from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import URL, create_engine, pool
from dotenv import load_dotenv

from app.core.database import Base

# Import models so Alembic can detect them
# Import all models so Alembic can detect them
import app.models


# Load .env
load_dotenv()


# Alembic configuration
config = context.config


# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Database settings
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")


# Create database URL safely
database_url = URL.create(
    drivername="mysql+pymysql",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=int(DB_PORT),
    database=DB_NAME,
)


# SQLAlchemy models metadata
target_metadata = Base.metadata


def run_migrations_offline() -> None:

    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named"
        },
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:

    connectable = create_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():

    run_migrations_offline()

else:

    run_migrations_online()