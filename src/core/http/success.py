from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def success(status: int, msg: str, data: Any = None) -> JSONResponse:
    content: dict[str, Any] = {"status": status, "msg": msg}
    if data is not None:
        content["data"] = jsonable_encoder(data)
    return JSONResponse(status_code=status, content=content)
