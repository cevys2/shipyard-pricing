from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash

from app.config import settings
from app.database import engine

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return generate_password_hash(password, method="pbkdf2:sha256")


def verify_password(plain: str, hashed: str) -> bool:
    return check_password_hash(hashed, plain)


def create_access_token(username: str, role: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> dict:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(
            creds.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        username = payload.get("sub")
        role = payload.get("role")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"username": username, "role": role}
    except JWTError as e:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from e


def require_admin(user: Annotated[dict, Depends(get_current_user)]) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def authenticate_user(username: str, password: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT password_hash, role FROM users WHERE username = :u"),
            {"u": username},
        ).fetchone()
    if not row or not verify_password(password, row[0]):
        return None
    return {"username": username, "role": row[1]}
