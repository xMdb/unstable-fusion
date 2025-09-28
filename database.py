# GENERATIVE AI DISCLAIMER
#
# A portion of this code was generated with the assistance of generative AI. Any files that do not contain a disclaimer were either written by a human without AI assistance or generated with developer tooling such as Vite.

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker, declarative_base
from config import DB_URL

# Database engine and session setup
# PostgreSQL-optimized engine configuration
engine = sa.create_engine(
    DB_URL, 
    future=True, 
    pool_pre_ping=True,
    pool_recycle=3600,  # Recycle connections every hour
    pool_size=5,        # Connection pool size
    max_overflow=10     # Additional connections when pool is full
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)