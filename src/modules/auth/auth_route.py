from uuid import UUID

from fastapi import APIRouter, Request

from ...core.security.principal import current_principal
from .handlers.auth_handlers import (
    ChangePasswordRequest,
    LoginRequest,
    MfaCodeRequest,
    MfaDisableRequest,
    MfaLoginRequest,
    PasswordConfirmRequest,
    authHandler,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(request: Request, body: LoginRequest):
    return await authHandler.login(request, body)


@router.post("/login/mfa")
async def login_mfa(request: Request, body: MfaLoginRequest):
    return await authHandler.mfa_login(request, body)


@router.post("/logout")
async def logout(request: Request):
    return await authHandler.logout(request)


@router.get("/me")
async def me(request: Request):
    return await authHandler.me(current_principal(request))


@router.put("/password")
async def change_password(request: Request, body: ChangePasswordRequest):
    return await authHandler.change_password(current_principal(request), body)


@router.get("/mfa")
async def mfa_status(request: Request):
    return await authHandler.mfa_status(current_principal(request))


@router.post("/mfa/setup")
async def mfa_setup(request: Request, body: PasswordConfirmRequest):
    return await authHandler.mfa_setup(current_principal(request), body)


@router.post("/mfa/enable")
async def mfa_enable(request: Request, body: MfaCodeRequest):
    return await authHandler.mfa_enable(current_principal(request), body)


@router.post("/mfa/disable")
async def mfa_disable(request: Request, body: MfaDisableRequest):
    return await authHandler.mfa_disable(current_principal(request), body)


@router.get("/sessions")
async def my_sessions(request: Request):
    return await authHandler.my_sessions(current_principal(request))


@router.post("/sessions/revoke-others")
async def revoke_my_other_sessions(request: Request, body: PasswordConfirmRequest):
    return await authHandler.revoke_my_other_sessions(current_principal(request), body)


@router.post("/sessions/{session_id}/revoke")
async def revoke_my_session(request: Request, session_id: UUID, body: PasswordConfirmRequest):
    return await authHandler.revoke_my_session(current_principal(request), session_id, body)
