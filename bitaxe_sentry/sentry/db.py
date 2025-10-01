import datetime
import os
import pathlib

from sqlmodel import Field, Session, SQLModel, create_engine

DB_URL = os.getenv("DB_URL", None)
if not DB_URL:
    env_path = os.getenv("DB_PATH")
    if env_path:
        DB_PATH = pathlib.Path(env_path)
    else:
        # Otherwise fall back to best-effort local defaults
        if os.path.exists("/app/data"):
            DB_PATH = pathlib.Path("/app/data") / "bitaxe_sentry.db"
        else:
            project_root = pathlib.Path(__file__).parent.parent.parent
            data_dir = project_root / "data"
            if data_dir.exists():
                DB_PATH = data_dir / "bitaxe_sentry.db"
            else:
                DB_PATH = pathlib.Path(__file__).parent.parent / "bitaxe_sentry.db"
    DB_URL = f"sqlite:///{DB_PATH}"


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
    stratumDiff: int = Field(default=0)
    sharesAccepted: int = Field(default=0)
    sharesRejected: int = Field(default=0)
    currentStratumUrl: str = Field(default="")
    # Additional fields can be added here as needed


# Create SQLite engine
engine = create_engine(DB_URL, echo=False)


def init_db():
    """Initialize the database by creating all tables."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Get a database session."""
    with Session(engine) as session:
        yield session
