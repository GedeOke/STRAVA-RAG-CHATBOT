# apps/backend/reset_db.py
from app.db import engine, Base
from sqlalchemy import text

# WAJIB: import models biar tabel terdaftar di Base.metadata
from app import models  

print("⚡ Reset DB start...")

# pastikan extension pgvector ada
with engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    print("✅ Extension pgvector dicek/aktif.")

# drop semua tabel
print("🗑️  Drop all tables...")
Base.metadata.drop_all(bind=engine)

# create ulang tabel
print("🛠️  Create all tables...")
Base.metadata.create_all(bind=engine)

print("✅ Semua tabel berhasil dibuat ulang dari models.py")
