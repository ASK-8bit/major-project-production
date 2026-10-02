from supabase import create_client, Client
from dotenv import load_dotenv
import os
<<<<<<< HEAD
from pathlib import Path

# Load .env from backend directory if present, or cwd
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()
=======

load_dotenv()
>>>>>>> 69c33f55ef38b287610ab76ea827993be9df31a5

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        supabase = None