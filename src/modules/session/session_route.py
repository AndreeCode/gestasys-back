from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from ...core.security.permission_guard import require_permission
from ...core.security.principal import current_principal
from .handlers.session_handlers import sessionHandler

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", dependencies=[Depends(require_permission("session.get"))])
async def get_all_sessions(
    request: Request,
    user_id: Optional[str] = None,
    device_id: Optional[str] = None,
    active: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return await sessionHandler.get_all(current_principal(request).session_id, user_id, device_id, active, limit, offset)


@router.get("/{session_id}", dependencies=[Depends(require_permission("session.get"))])
async def get_session_by_id(request: Request, session_id: str):
    return await sessionHandler.get_by_id(current_principal(request).session_id, session_id)


@router.delete("/{session_id}", dependencies=[Depends(require_permission("session.delete"))])
async def delete_session(request: Request, session_id: str):
    return await sessionHandler.delete(current_principal(request).session_id, session_id)
