import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mls_grader.db")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_MODEL_FAST = os.getenv("OPENROUTER_MODEL_FAST", OPENROUTER_MODEL)
OPENROUTER_MODEL_DEEP = os.getenv("OPENROUTER_MODEL_DEEP", "openai/gpt-4.1-mini")
TOP_DEFAULT = int(os.getenv("TOP_DEFAULT", "10"))
APP_API_KEY = os.getenv("APP_API_KEY", "")
