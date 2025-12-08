import os
from sqlmodel import SQLModel, create_engine, Session

# Use PostgreSQL in production, SQLite for local development
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./marketplace.db")

# Fix for Render: they provide postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Different connection args for SQLite vs PostgreSQL
connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)


def init_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session