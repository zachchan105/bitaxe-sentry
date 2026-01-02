from sqlmodel import SQLModel, Field, create_engine, Session, select
import datetime
import pathlib
import os
import logging

logger = logging.getLogger(__name__)

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


def run_migrations():
    """Run Alembic migrations to update database schema."""
    try:
        from alembic import command
        from alembic.config import Config
        
        # Try multiple paths to find alembic.ini (works in both dev and Docker)
        possible_paths = [
            pathlib.Path(__file__).parent.parent.parent / "alembic.ini",  # Project root
            pathlib.Path("/app/alembic.ini"),  # Docker container
            pathlib.Path.cwd() / "alembic.ini",  # Current working directory
        ]
        
        alembic_ini_path = None
        for path in possible_paths:
            if path.exists():
                alembic_ini_path = path
                break
        
        if not alembic_ini_path:
            logger.warning("Could not find alembic.ini file, skipping migrations")
            return
        
        # Load config - Alembic resolves script_location relative to alembic.ini location
        alembic_cfg = Config(str(alembic_ini_path))
        
        # Override database URL (since it's set dynamically)
        alembic_cfg.set_main_option('sqlalchemy.url', f'sqlite:///{DB_PATH}')
        
        logger.info(f"Running database migrations from {alembic_ini_path}...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully")
    except Exception as e:
        logger.warning(f"Could not run migrations: {e}. This is OK if Alembic is not installed or this is a fresh install.")
        # If migrations fail, we'll still try to create tables (for fresh installs)


def init_db():
    """Initialize the database by creating all tables and running migrations."""
    # First, ensure tables exist (for fresh installs)
    SQLModel.metadata.create_all(engine)
    
    # Then run migrations (for existing databases that need schema updates)
    run_migrations()


def get_session():
    """Get a database session."""
    with Session(engine) as session:
        yield session 