from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.auth import authenticate_user, create_access_token, get_current_user, hash_password, require_admin
from app.database import engine
from app.schemas.auth import LoginRequest, PasswordChange, TokenResponse, UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    user = authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Username atau password salah")
    token = create_access_token(user["username"], user["role"])
    return TokenResponse(
        access_token=token,
        username=user["username"],
        role=user["role"],
    )


@router.get("/me")
def me(user: Annotated[dict, Depends(get_current_user)]):
    return user


users_router = APIRouter(prefix="/users", tags=["users"])


@users_router.get("", response_model=list[UserOut])
def list_users(_: Annotated[dict, Depends(require_admin)]):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, username, role FROM users ORDER BY id")).fetchall()
    return [UserOut(id=r[0], username=r[1], role=r[2]) for r in rows]


@users_router.post("", response_model=UserOut)
def create_user(body: UserCreate, _: Annotated[dict, Depends(require_admin)]):
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM users WHERE username = :u"), {"u": body.username}
        ).fetchone()
        if exists:
            raise HTTPException(status_code=400, detail="Username sudah terdaftar")
        conn.execute(
            text("INSERT INTO users (username, password_hash, role) VALUES (:u, :p, :r)"),
            {"u": body.username, "p": hash_password(body.password), "r": body.role},
        )
        row = conn.execute(
            text("SELECT id, username, role FROM users WHERE username = :u"),
            {"u": body.username},
        ).fetchone()
    return UserOut(id=row[0], username=row[1], role=row[2])


@users_router.delete("/{username}")
def delete_user(username: str, admin: Annotated[dict, Depends(require_admin)]):
    if username == "admin":
        raise HTTPException(status_code=400, detail="Akun admin utama tidak boleh dihapus")
    if username == admin["username"]:
        raise HTTPException(status_code=400, detail="Tidak bisa hapus akun sendiri")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE username = :u"), {"u": username})
    return {"ok": True}


@users_router.post("/password")
def change_password(body: PasswordChange, _: Annotated[dict, Depends(require_admin)]):
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET password_hash = :p WHERE username = :u"),
            {"p": hash_password(body.new_password), "u": body.username},
        )
    return {"ok": True}
