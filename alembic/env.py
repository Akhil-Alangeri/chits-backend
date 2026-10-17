from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from dotenv import load_dotenv

from app.core.database import Base, DATABASE_URL

# Import all models so Alembic can detect them
import app.models
from app.services.customer.msg91_auth.msg91_cooldown import Msg91LoginState


# Load .env
load_dotenv()


# Alembic configuration
config = context.config


# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)





# Create database URL safely



# SQLAlchemy models metadata
target_metadata = Base.metadata


def run_migrations_offline() -> None:

    context.configure(
        url=DATABASE_URL,
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
        DATABASE_URL,
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