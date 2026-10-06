import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
VECTOR_STORE_DIR = DATA_DIR / "vector_store"
DB_PATH = DATA_DIR / "app.db"

# Ensure essential directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)

class Settings(BaseSettings):
    APP_NAME: str = "DocuMind AI - Intelligent Document QA"
    VERSION: str = "2.0.0"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    
    # LLM Settings (can be overridden via UI Settings or environment)
    DEFAULT_PROVIDER: str = "gemini"  # "gemini", "openai", "groq", "local"
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    
    # Model defaults
    GEMINI_MODEL: str = "gemini-2.5-flash"
    OPENAI_MODEL: str = "gpt-4o-mini"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    
    # RAG Settings
    CHUNK_SIZE: int = 750
    CHUNK_OVERLAP: int = 150
    TOP_K: int = 5
    HYBRID_SEARCH: bool = True
    SIMILARITY_THRESHOLD: float = 0.35
    
    # Maximum upload size in MB
    MAX_UPLOAD_SIZE_MB: int = 60

settings = Settings()
