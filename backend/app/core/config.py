from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
import sys

# Load .env file kalau ada
load_dotenv()


class Settings(BaseSettings):
    # === PROJECT INFO ===
    PROJECT_NAME: str = Field("Strava RAG Chatbot", description="Nama proyek")
    VERSION: str = Field("1.0.0", description="Versi aplikasi")

    # === CHROMA ===
    CHROMA_PATH: str = Field("./db", description="Folder penyimpanan ChromaDB")
    CHROMA_COLLECTION: str = Field("strava_club", description="Nama koleksi ChromaDB")

    # === GOOGLE SHEET ===
    GSHEET_NAME: str = Field("StravaClubData", description="Nama file Google Sheet")
    GSHEET_TAB: str = Field("ClubActivities", description="Nama tab di Google Sheet")
    GSHEET_CRED_FILE: str = Field("credentials.json", description="File kredensial Google API")
    GSHEET_ID: str = Field("", description="ID Google Sheet (opsional, gunakan ini untuk menghindari Drive API)")

    # === EMBEDDING MODEL ===
    EMBEDDING_MODEL: str = Field(
        "sentence-transformers/all-MiniLM-L6-v2",
        description="Model untuk embedding teks",
    )

    # === APP SETTINGS ===
    PORT: int = Field(8000, description="Port FastAPI")
    HOST: str = Field("0.0.0.0", description="Host FastAPI")

    # === LLM SETTINGS ===
    LLM_PROVIDER: str = Field("none", description="Penyedia LLM: groq | openai | none")
    OPENAI_MODEL: str = Field("gpt-4o-mini", description="Model OpenAI default")
    GROQ_MODEL: str = Field("llama-3.1-8b-instant", description="Model Groq default")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


# ===========================
# Safe initialization
# ===========================
try:
    settings = Settings()
    print(f"[CONFIG] Loaded successfully: {settings.PROJECT_NAME}")
    print(f"   - Chroma Path: {settings.CHROMA_PATH}")
    print(f"   - GSheet Name: {settings.GSHEET_NAME}")
    print(f"   - Embedding Model: {settings.EMBEDDING_MODEL}")
    print(f"   - LLM Provider: {settings.LLM_PROVIDER}")
    if settings.LLM_PROVIDER.lower() == "groq":
        print(f"   - Groq Model: {settings.GROQ_MODEL}")
    elif settings.LLM_PROVIDER.lower() == "openai":
        print(f"   - OpenAI Model: {settings.OPENAI_MODEL}")

except Exception as e:
    print("[CONFIG ERROR] Gagal memuat konfigurasi environment.")
    print(f"   Detail: {e}", file=sys.stderr)

    # fallback default (biar gak crash di container)
    settings = Settings(
        CHROMA_PATH="./db",
        GSHEET_NAME="StravaClubData",
        GSHEET_TAB="ClubActivities",
    )
    print("Menggunakan fallback default configuration...")
