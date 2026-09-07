from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import psycopg
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7
PBKDF2_ITERATIONS = 210_000

_user_store: UserStore | None = None
_jwt_secret: str = ""

security_bearer = HTTPBearer(auto_error=False)


def configure_auth(store: UserStore, jwt_secret: str) -> None:
    global _user_store, _jwt_secret
    _user_store = store
    _jwt_secret = jwt_secret


def resolve_jwt_secret() -> str:
    raw = (os.getenv("JWT_SECRET") or "").strip()
    if not raw:
        raise RuntimeError("JWT_SECRET must be set in base_Platform/.env")
    return raw


def hash_password(plain: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        plain.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt_b64}${digest_b64}"


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        parts = password_hash.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = base64.urlsafe_b64decode(parts[2].encode("ascii"))
        expected = base64.urlsafe_b64decode(parts[3].encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            plain.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_access_token(*, user_id: int, username: str, role: str) -> str:
    if not _jwt_secret:
        raise RuntimeError("JWT secret not configured")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)).timestamp()),
    }
    return jwt.encode(payload, _jwt_secret, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    if not _jwt_secret:
        raise RuntimeError("JWT secret not configured")
    return jwt.decode(token, _jwt_secret, algorithms=[JWT_ALGORITHM])


class UserStore:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise RuntimeError("database_url is required for UserStore")
        self._lock = threading.Lock()
        self._conn = psycopg.connect(database_url, row_factory=dict_row)
        self._conn.autocommit = False
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
                    is_active BOOLEAN NOT NULL DEFAULT true,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at DESC)"
            )
            self._conn.commit()
        self._ensure_seed_admin()

    def _ensure_seed_admin(self) -> None:
        seed_admin_username = (os.getenv("SEED_ADMIN_USERNAME") or "").strip()
        seed_admin_password = (os.getenv("SEED_ADMIN_PASSWORD") or "").strip()
        if not seed_admin_username or not seed_admin_password:
            raise RuntimeError(
                "SEED_ADMIN_USERNAME and SEED_ADMIN_PASSWORD must be set in base_Platform/.env"
            )
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM users WHERE username = %s",
                (seed_admin_username,),
            ).fetchone()
            if row:
                self._conn.rollback()
                return
            ph = hash_password(seed_admin_password)
            self._conn.execute(
                """
                INSERT INTO users (username, password_hash, role, is_active)
                VALUES (%s, %s, 'admin', true)
                """,
                (seed_admin_username, ph),
            )
            self._conn.commit()

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        u = username.strip()
        if not u:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT id, username, password_hash, role, is_active, created_at, updated_at FROM users WHERE username = %s",
                (u,),
            ).fetchone()
        return dict(row) if row else None

    def get_by_id(self, user_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, username, password_hash, role, is_active, created_at, updated_at FROM users WHERE id = %s",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_user(
        self,
        *,
        username: str,
        password: str,
        role: str = "user",
    ) -> dict[str, Any]:
        u = username.strip()
        if not u:
            raise ValueError("username is empty")
        if role not in {"admin", "user"}:
            raise ValueError("invalid role")
        ph = hash_password(password)
        with self._lock:
            try:
                cur = self._conn.execute(
                    """
                    INSERT INTO users (username, password_hash, role, is_active)
                    VALUES (%s, %s, %s, true)
                    RETURNING id, username, role, is_active, created_at, updated_at
                    """,
                    (u, ph, role),
                )
                row = cur.fetchone()
                self._conn.commit()
            except psycopg.errors.UniqueViolation:
                self._conn.rollback()
                raise ValueError("username already exists") from None
        return dict(row) if row else {}

    def list_users(self, limit: int = 500) -> list[dict[str, Any]]:
        lim = max(1, min(limit, 2000))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, username, role, is_active, created_at, updated_at
                FROM users ORDER BY id ASC LIMIT %s
                """,
                (lim,),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_active_admins(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role = 'admin' AND is_active = true"
            ).fetchone()
        return int(row["c"]) if row else 0

    def update_user(
        self,
        user_id: int,
        *,
        role: str | None = None,
        is_active: bool | None = None,
        password: str | None = None,
        actor_id: int,
    ) -> dict[str, Any] | None:
        target = self.get_by_id(user_id)
        if not target:
            return None
        sets: list[str] = []
        params: list[Any] = []
        if password is not None:
            if len(password) < 6:
                raise ValueError("password too short")
            sets.append("password_hash = %s")
            params.append(hash_password(password))
        if role is not None:
            if role not in {"admin", "user"}:
                raise ValueError("invalid role")
            sets.append("role = %s")
            params.append(role)
        if is_active is not None:
            sets.append("is_active = %s")
            params.append(is_active)
        if not sets:
            return self.public_row(target)
        if (
            actor_id == user_id
            and is_active is False
            and target.get("role") == "admin"
            and self.count_active_admins() <= 1
        ):
            raise ValueError("cannot disable the only active admin")
        if (
            actor_id == user_id
            and role == "user"
            and target.get("role") == "admin"
            and self.count_active_admins() <= 1
        ):
            raise ValueError("cannot demote the only active admin")
        params.append(user_id)
        sql = f"UPDATE users SET {', '.join(sets)}, updated_at = now() WHERE id = %s RETURNING id, username, role, is_active, created_at, updated_at"
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
            self._conn.commit()
        return dict(row) if row else None

    @staticmethod
    def public_row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "is_active": row["is_active"],
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        row = self.get_by_username(username)
        if not row or not row.get("is_active"):
            return None
        if not verify_password(password, str(row["password_hash"])):
            return None
        return self.public_row(row)

    def user_from_access_token(self, token: str) -> dict[str, Any]:
        payload = decode_token(token)
        sub = payload.get("sub")
        if sub is None:
            raise ValueError("invalid token")
        uid = int(sub)
        row = self.get_by_id(uid)
        if not row or not row.get("is_active"):
            raise ValueError("user inactive or missing")
        return self.public_row(row)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class AdminCreateUserRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(default="user")

    def normalized_role(self) -> str:
        r = (self.role or "user").strip().lower()
        if r not in {"admin", "user"}:
            raise ValueError("role must be admin or user")
        return r


class AdminPatchUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)

    def normalized_role(self) -> str | None:
        if self.role is None:
            return None
        r = self.role.strip().lower()
        if r not in {"admin", "user"}:
            raise ValueError("role must be admin or user")
        return r


def get_user_store() -> UserStore:
    if _user_store is None:
        raise HTTPException(status_code=500, detail="User store not initialized")
    return _user_store


async def require_user(
    cred: HTTPAuthorizationCredentials | None = Depends(security_bearer),
) -> dict[str, Any]:
    if cred is None or (cred.scheme or "").lower() != "bearer":
        raise HTTPException(status_code=401, detail="未登录或缺少令牌")
    token = cred.credentials or ""
    if not token.strip():
        raise HTTPException(status_code=401, detail="未登录或缺少令牌")
    store = get_user_store()
    try:
        return store.user_from_access_token(token.strip())
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的登录令牌") from None
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


async def require_admin(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def user_from_websocket_token(token: str | None) -> dict[str, Any] | None:
    if not token or not token.strip():
        return None
    store = _user_store
    if store is None:
        return None
    try:
        return store.user_from_access_token(token.strip())
    except Exception:
        return None
