from typing import Dict, Any
from agent.schemas import Plan, ToolResult
from agent.tools import TOOL_REGISTRY
from services.analytical_pipeline import _get_repo_url


class PlanExecutor:
    def __init__(self, session_id: str, user_query: str):
        self.session_id = session_id
        self.user_query = user_query
        self.step_outputs: Dict[str, Any] = {}
        self.repo_url = _get_repo_url(session_id)

    def _resolve_arg(self, value: Any) -> Any:
        """Resolve references like 'step_1' or nested dicts."""
        if isinstance(value, str) and value in self.step_outputs:
            return self.step_outputs[value]
        if isinstance(value, dict):
            return {k: self._resolve_arg(v) for k, v in value.items()}
        return value

    def _run_single_step(self, step) -> ToolResult:
        tool_name = step.tool
        if tool_name not in TOOL_REGISTRY:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

        # Resolve arguments that reference previous steps
        resolved_args = {}
        for key, value in step.args.items():
            if key.endswith("_from"):
                # e.g. function_code_from → function_code
                real_key = key.replace("_from", "")
                source_step = value
                if source_step not in self.step_outputs:
                    return ToolResult(success=False, error=f"Missing output from {source_step}")
                output = self.step_outputs[source_step]

                # Smart extraction
                if real_key == "function_code":
                    resolved_args["function_code"] = output.get("function_code") or output.get("data", {}).get("function_code")
                elif real_key == "code" or real_key == "file_content":
                    resolved_args["file_content"] = output.get("content") or output.get("data", {}).get("content")
                else:
                    resolved_args[real_key] = output
            else:
                resolved_args[key] = self._resolve_arg(value)

        # Inject common context
        if tool_name == "github_fetch_file":
            if not self.repo_url:
                return ToolResult(success=False, error="No repo_url found for this session")
            resolved_args["repo_url"] = self.repo_url

        if tool_name == "classic_rag_retrieve":
            resolved_args["session_id"] = self.session_id

        if tool_name == "generate_analytical_function":
            # file_content should already be resolved
            if "file_content" not in resolved_args:
                return ToolResult(success=False, error="generate_analytical_function requires file content")

        if tool_name == "supabase_store_function":
            resolved_args.setdefault("sample_query", self.user_query)

        print(f"[Executor] Running {tool_name} with args keys: {list(resolved_args.keys())}")

        try:
            result = TOOL_REGISTRY[tool_name](**resolved_args)
            return result
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def execute(self, plan: Plan) -> Dict[str, Any]:
        for step in plan.steps:
            result = self._run_single_step(step)

            if not result.success:
                return {
                    "success": False,
                    "error": f"Step {step.id} ({step.tool}) failed: {result.error}",
                    "step_outputs": self.step_outputs
                }

            # Store useful output
            self.step_outputs[step.id] = result.data

        return {
            "success": True,
            "step_outputs": self.step_outputs,
            "needs_final_explanation": plan.needs_final_explanation
        }