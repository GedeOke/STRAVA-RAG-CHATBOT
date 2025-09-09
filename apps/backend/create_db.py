from app.db import engine, Base
from app import models  # penting: import models biar Base tahu semua tabel

print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("Done.")