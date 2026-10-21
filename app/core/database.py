import os

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
INSTANCE_UNIX_SOCKET = os.getenv("INSTANCE_UNIX_SOCKET")


if INSTANCE_UNIX_SOCKET:
    # Production - Google Cloud Run → Cloud SQL
    DATABASE_URL = URL.create(
        drivername="mysql+pymysql",
        username=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        query={
            "unix_socket": INSTANCE_UNIX_SOCKET,
        },
    )
else:
    # Local development
    DATABASE_URL = URL.create(
        drivername="mysql+pymysql",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=int(DB_PORT),
        database=DB_NAME,
    )


engine = create_engine(
    DATABASE_URL,
    # Keep SQL NOW() defaults consistent with Python datetime.utcnow timestamps.
    connect_args={"init_command": "SET time_zone = '+00:00'"},
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=5,
    max_overflow=5,
)


SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


Base = declarative_base()


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()