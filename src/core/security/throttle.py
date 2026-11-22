import time
from collections import defaultdict, deque

from fastapi import Request

from ..http.app_error import AppError
from ..logger.logger import logger
from .principal import current_principal

_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
MAX_TRACKED = 10000


def throttle(action: str, limit: int, window_seconds: int):
    async def dependency(request: Request) -> None:
        principal = current_principal(request)
        key = (action, str(principal.user_id))
        now = time.monotonic()
        bucket = _hits[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            logger.warning(f"429 limite de {action} alcanzado por {principal.username}")
            raise AppError(429, f"Demasiadas solicitudes de este tipo, espera {max(1, window_seconds // 60)} minuto(s) e intenta de nuevo")
        bucket.append(now)
        if len(_hits) > MAX_TRACKED:
            for stale in [k for k, v in _hits.items() if not v or now - v[-1] > 3600]:
                _hits.pop(stale, None)

    return dependency
