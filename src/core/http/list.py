from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def list_response(status: int, msg: str, data: Any = None, meta: Any = None) -> JSONResponse:
    content: dict[str, Any] = {"status": status, "msg": msg}
    if data is not None:
        content["data"] = jsonable_encoder(data)
    if meta is not None:
        content["meta"] = jsonable_encoder(meta)
    return JSONResponse(status_code=status, content=content)
