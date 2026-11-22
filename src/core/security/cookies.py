from fastapi.responses import Response

from ..config.config import config

ACCESS_TOKEN_COOKIE = "access_token"
DEVICE_TOKEN_COOKIE = "device_token"
DEVICE_TOKEN_MAX_AGE = 400 * 24 * 60 * 60


def _samesite() -> str:
    return config.cookie_samesite if config.cookie_samesite in ("lax", "strict", "none") else "lax"


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        httponly=True,
        secure=config.cookie_secure,
        samesite=_samesite(),
        max_age=config.jwt_expire_minutes * 60,
        domain=config.cookie_domain,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=ACCESS_TOKEN_COOKIE, path="/", domain=config.cookie_domain)


def set_device_cookie(response: Response, device_token: str) -> None:
    response.set_cookie(
        key=DEVICE_TOKEN_COOKIE,
        value=device_token,
        httponly=True,
        secure=config.cookie_secure,
        samesite=_samesite(),
        max_age=DEVICE_TOKEN_MAX_AGE,
        domain=config.cookie_domain,
        path="/",
    )
