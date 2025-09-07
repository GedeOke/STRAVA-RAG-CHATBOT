from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .settings import DATABASE_URL

# bikin engine
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# session factory
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# base class buat semua models
class Base(DeclarativeBase):
    pass

# dependency FastAPI untuk dapetin session per-request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
