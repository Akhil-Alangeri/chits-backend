import bcrypt
import os
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError


# =========================================================
# JWT CONFIG
# =========================================================

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET")

ALGORITHM = "HS256"

# 5 * 60 = 300 minutes = 5 HOURS
ACCESS_TOKEN_EXPIRE_MINUTES = 5 * 60


# =========================================================
# PASSWORD HASH
# =========================================================

def hash_password(password: str) -> str:

    password_bytes = password.encode("utf-8")

    hashed = bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt()
    )

    return hashed.decode("utf-8")


# =========================================================
# PASSWORD VERIFY
# =========================================================

def verify_password(
    plain_password: str,
    hashed_password: str
) -> bool:

    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8")
    )


# =========================================================
# CREATE ACCESS TOKEN
# =========================================================

def create_access_token(
    data: dict,
    expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES
) -> str:

    # Current UTC time
    now = datetime.now(timezone.utc)

    # Copy the data provided by the caller
    payload = data.copy()

    # Calculate expiry time
    expire = now + timedelta(
        minutes=expires_minutes
    )

    # =====================================================
    # JWT CLAIMS
    # =====================================================

    payload.update({

        # Token issued time
        "iat": now,

        # Token expiry time
        "exp": expire,

    })

    # =====================================================
    # CREATE JWT
    # =====================================================

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


# =========================================================
# DECODE ACCESS TOKEN
# =========================================================

def decode_access_token(token: str):

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        return payload

    except JWTError:

        return None