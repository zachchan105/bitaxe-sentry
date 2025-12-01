from sqlmodel import SQLModel, Field, create_engine, Session, select
import datetime
import pathlib
import os

env_path = os.getenv("DB_PATH")
if env_path:
    DB_PATH = pathlib.Path(env_path)
else:
    # Otherwise fall back to best-effort local defaults
    if os.path.exists('/app/data'):
        DB_PATH = pathlib.Path('/app/data') / "bitaxe_sentry.db"
    else:
        project_root = pathlib.Path(__file__).parent.parent.parent
        data_dir = project_root / "data"
        if data_dir.exists():
            DB_PATH = data_dir / "bitaxe_sentry.db"
        else:
            DB_PATH = pathlib.Path(__file__).parent.parent / "bitaxe_sentry.db"


class Miner(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str
    endpoint: str
    added_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


class Reading(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    miner_id: int = Field(foreign_key="miner.id")
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    hash_rate: float
    temperature: float
    best_diff: str
    voltage: float = Field(default=0.0)  # Voltage in millivolts
    error_percentage: float = Field(default=0.0)  # Error percentage
    # Additional fields can be added here as needed


# Create SQLite engine
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


def init_db():
    """Initialize the database by creating all tables."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Get a database session."""
    with Session(engine) as session:
        yield session 