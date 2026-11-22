from fastapi import APIRouter, Request

from ...core.security.principal import current_principal
from .handlers.auth_handlers import ChangePasswordRequest, LoginRequest, authHandler

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(request: Request, body: LoginRequest):
    return await authHandler.login(request, body)


@router.post("/logout")
async def logout(request: Request):
    return await authHandler.logout(request)


@router.get("/me")
async def me(request: Request):
    return await authHandler.me(current_principal(request))


@router.put("/password")
async def change_password(request: Request, body: ChangePasswordRequest):
    return await authHandler.change_password(current_principal(request), body)
