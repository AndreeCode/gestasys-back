import logging
from contextlib import asynccontextmanager
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config.config import config
from src.core.db.connection import close_pool, init_pool, ping
from src.core.http.exception_handlers import register_exception_handlers
from src.core.http.success import success
from src.core.logger.logger import logger
from src.core.routes.routes import router as api_router
from src.core.security.auth_middleware import AuthMiddleware
from src.modules.backup.services.backup_service import backupService


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    logger.info("Base de datos conectada correctamente")
    try:
        await backupService.mark_interrupted()
    except Exception as err:
        logger.error(f"No se pudieron marcar los backups interrumpidos: {err}")
    backupService.start_scheduler()
    yield
    await backupService.stop()
    await close_pool()


app = FastAPI(title="GestaSys API", lifespan=lifespan)

register_exception_handlers(app)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
    expose_headers=["Content-Disposition", "X-Total-Count"],
    max_age=600,
)
app.include_router(api_router, prefix="/api")


@app.get("/api")
async def root():
    return success(
        200,
        "servidor corriendo correctamente",
        {"service": "gestasys-back", "database": "ok" if await ping() else "error", "time": datetime.now().astimezone()},
    )
