from datetime import datetime, timezone
from typing import Any

import jwt

from ..config.config import config

ISSUER = "gestasys"


def create_access_token(data: dict[str, Any], expires_at: datetime) -> str:
    payload = {**data, "iss": ISSUER, "iat": datetime.now(timezone.utc), "exp": expires_at}
    return jwt.encode(payload, config.jwt_secret, algorithm=config.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        config.jwt_secret,
        algorithms=[config.jwt_algorithm],
        issuer=ISSUER,
        options={"require": ["exp", "sub", "sid"]},
    )
    return payload
