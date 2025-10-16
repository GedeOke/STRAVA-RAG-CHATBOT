import hashlib
import json
import re
from datetime import datetime
from functools import wraps
from app.core.logger import logger


# ==================================================
# TIME HELPERS
# ==================================================
def now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Return current time string in given format."""
    return datetime.now().strftime(fmt)


def format_time(seconds: int) -> str:
    """Convert detik ke format menit:detik (misal 125 -> 2:05)."""
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def parse_time_str(time_str: str) -> int:
    """
    Convert "MM:SS" atau "H:MM:SS" jadi detik.
    Contoh: "21:55" -> 1315
    """
    parts = [int(x) for x in time_str.split(":")]
    if len(parts) == 2:
        m, s = parts
        return m * 60 + s
    elif len(parts) == 3:
        h, m, s = parts
        return h * 3600 + m * 60 + s
    return 0


# ==================================================
# STRING & CLEANING HELPERS
# ==================================================
def clean_text(text: str) -> str:
    """Hapus spasi berlebih dan karakter aneh."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip())


def slugify(text: str) -> str:
    """Buat slug dari teks (misal nama member jadi id unik)."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def pretty_json(data) -> str:
    """Return JSON terformat cantik."""
    return json.dumps(data, indent=2, ensure_ascii=False)


# ==================================================
# HASH HELPERS
# ==================================================
def md5_hash(text: str) -> str:
    """Generate MD5 hash dari string."""
    return hashlib.md5(text.encode()).hexdigest()


def json_hash(data: dict) -> str:
    """Hash dari JSON dict (buat deteksi perubahan data)."""
    raw = json.dumps(data, sort_keys=True)
    return md5_hash(raw)


# ==================================================
# PERFORMANCE TIMER DECORATOR
# ==================================================
def timer(func):
    """Decorator buat ukur waktu eksekusi fungsi."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        start = datetime.now()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            duration = (datetime.now() - start).total_seconds()
            logger.info(f"{func.__name__} selesai dalam {duration:.2f} detik")

    return wrapper


# ==================================================
# TESTING SECTION
# ==================================================
if __name__ == "__main__":
    # test beberapa fungsi
    print("Sekarang:", now_str())
    print("Slugify:", slugify("Yoga Setiyawan"))
    print("Parse 21:55:", parse_time_str("21:55"))
    print("MD5 Hash:", md5_hash("Yoga 3km 21:55"))

