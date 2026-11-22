from fastapi.responses import JSONResponse

from ..logger.logger import logger


def error(status: int, msg: str, err: Exception | None = None) -> JSONResponse:
    if status >= 500:
        logger.error(f"{msg}: {err}", exc_info=err)
    else:
        logger.warning(f"{status} {msg}: {err}" if err else f"{status} {msg}")
    return JSONResponse(status_code=status, content={"status": status, "msg": msg})
