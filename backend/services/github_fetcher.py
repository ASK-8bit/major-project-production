import re
import requests


def _extract_owner_repo(repo_url: str) -> tuple[str, str]:
    """
    Extract owner and repo name from GitHub URL.
    Handles:
      https://github.com/owner/repo
      https://github.com/owner/repo.git
      https://github.com/owner/repo/
    """
    repo_url = repo_url.rstrip("/").removesuffix(".git")
    match = re.match(r"https://github\.com/([^/]+)/([^/]+)", repo_url)

    if not match:
        raise ValueError(
            f"[GitHubFetcher] ERROR: Cannot parse GitHub URL: {repo_url}. "
            f"Expected format: https://github.com/owner/repo"
        )

    owner = match.group(1)
    repo = match.group(2)
    return owner, repo


def fetch_file(repo_url: str, file_path: str) -> str:
    """
    Fetch raw file content from GitHub.
    Tries 'main' branch first, then 'master'.

    Args:
        repo_url: Full GitHub repo URL (from sessions.repo_url)
        file_path: Relative file path in repo (e.g. "backend/services/payments.py")

    Returns:
        File content as string.

    Raises:
        FileNotFoundError if file not found on either branch.
        ValueError if repo URL is invalid.
    """
    owner, repo = _extract_owner_repo(repo_url)

    file_path = file_path.lstrip("/")

    branches_to_try = ["main"]

    for branch in branches_to_try:
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}"

        try:
            response = requests.get(raw_url, timeout=10)

            if response.status_code == 200:
                print(f"[GitHubFetcher] Successfully fetched: {file_path} (branch: {branch})")
                return response.text

            elif response.status_code == 404:
                print(f"[GitHubFetcher] File not found on branch '{branch}': {raw_url}")
                continue

            else:
                print(
                    f"[GitHubFetcher] ERROR: Unexpected status {response.status_code} "
                    f"for URL: {raw_url}"
                )
                continue

        except requests.Timeout:
            print(f"[GitHubFetcher] ERROR: Request timed out for URL: {raw_url}")
            continue

        except requests.RequestException as e:
            print(f"[GitHubFetcher] ERROR: Network error fetching {raw_url}: {e}")
            continue

    raise FileNotFoundError(
        f"[GitHubFetcher] ERROR: Could not fetch '{file_path}' from repo '{repo_url}'. "
        f"Tried branches: {branches_to_try}. "
        f"Check that the file path is correct and the repo is public."
    )