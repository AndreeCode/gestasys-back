import time
from collections import defaultdict, deque

from ....core.config.config import config

_attempts: dict[str, deque[float]] = defaultdict(deque)
WINDOW_SECONDS = 60


def allow_login_attempt(ip: str | None) -> bool:
    key = ip or "unknown"
    now = time.monotonic()
    bucket = _attempts[key]
    while bucket and now - bucket[0] > WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= config.login_rate_limit:
        return False
    bucket.append(now)
    if len(_attempts) > 10000:
        for stale in [k for k, v in _attempts.items() if not v or now - v[-1] > WINDOW_SECONDS]:
            _attempts.pop(stale, None)
    return True
