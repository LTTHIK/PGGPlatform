"""IR / CRR 占位路由（第二阶段）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..auth_users import require_user

router = APIRouter()


@router.get("/overview")
def ir_overview(_user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return {"status": "stub", "message": "IR module not implemented in phase 1"}
