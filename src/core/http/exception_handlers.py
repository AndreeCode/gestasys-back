import asyncpg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .app_error import AppError
from .error import error

CONSTRAINT_MESSAGES: dict[str, str] = {}


def register_constraints(messages: dict[str, str]) -> None:
    CONSTRAINT_MESSAGES.update(messages)


def describe_db_error(exc: asyncpg.PostgresError) -> tuple[int, str]:
    name = getattr(exc, "constraint_name", None)
    if name and name in CONSTRAINT_MESSAGES:
        return (409 if isinstance(exc, asyncpg.UniqueViolationError) else 400), CONSTRAINT_MESSAGES[name]
    if isinstance(exc, asyncpg.UniqueViolationError):
        return 409, "Ya existe un registro con esos datos"
    if isinstance(exc, asyncpg.ForeignKeyViolationError):
        return 400, "Hace referencia a un registro que no existe o esta en uso"
    if isinstance(exc, (asyncpg.CheckViolationError, asyncpg.NotNullViolationError, asyncpg.DataError)):
        return 400, f"Datos invalidos: {exc}"
    if isinstance(exc, asyncpg.RaiseError):
        return 400, str(exc)
    return 500, "Error de base de datos"


def database_error(exc: asyncpg.PostgresError):
    status, msg = describe_db_error(exc)
    return error(status, msg, exc)


def register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return error(exc.status, exc.msg)

    @app.exception_handler(asyncpg.PostgresError)
    async def postgres_error_handler(request: Request, exc: asyncpg.PostgresError):
        return database_error(exc)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        details = []
        for err in exc.errors():
            field = ".".join(str(part) for part in err["loc"] if part not in ("body", "query", "path"))
            details.append(f"{field}: {err['msg']}" if field else err["msg"])
        msg = "; ".join(details) if details else "Datos de la solicitud invalidos"
        return error(422, msg)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        messages = {404: "Ruta no encontrada", 405: "Metodo no permitido"}
        return error(exc.status_code, messages.get(exc.status_code, str(exc.detail)), exc)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return error(500, "Error interno del servidor", exc)
