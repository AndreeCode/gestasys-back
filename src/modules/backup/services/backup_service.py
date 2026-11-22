import asyncio
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import UUID

from ....core.config.config import config
from ....core.db.connection import connection, transaction
from ....core.http.app_error import AppError, BadRequestError, ConflictError, NotFoundError
from ....core.logger.logger import logger
from ..domain.backup_domain import Backup
from ..repositories.backup_repositories import backupRepository

DUMP_TIMEOUT_SECONDS = 30 * 60


def backup_dir() -> Path:
    return Path(config.backup_dir).resolve()


def pg_dump_available() -> bool:
    return shutil.which(config.pg_dump_path) is not None


def next_run(now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now().astimezone()
    run = now.replace(hour=config.backup_hour, minute=config.backup_minute, second=0, microsecond=0)
    return run if run > now else run + timedelta(days=1)


class BackupService:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()
        self._scheduler: Optional[asyncio.Task] = None

    async def get_all(self, kind=None, status=None, limit: int = 25, offset: int = 0) -> tuple[list[Backup], int]:
        async with connection() as conn:
            return await backupRepository.get_all(conn, kind, status, limit, offset)

    async def get_by_id(self, backup_id: UUID) -> Backup:
        async with connection() as conn:
            backup = await backupRepository.get_by_id(conn, backup_id)
        if backup is None:
            raise NotFoundError("Backup no encontrado")
        return backup

    async def status(self) -> dict:
        async with connection() as conn:
            last = await backupRepository.latest(conn, "completed")
            failure = await backupRepository.latest(conn, "failed")
            summary = await backupRepository.summary(conn)
        return {
            "auto_enabled": config.backup_auto,
            "schedule": f"{config.backup_hour:02d}:{config.backup_minute:02d}",
            "next_run_at": next_run() if config.backup_auto else None,
            "keep": config.backup_keep,
            "pg_dump_available": pg_dump_available(),
            "running": summary["running"],
            "total_size_bytes": summary["total_size_bytes"],
            "last_backup": last.to_dict() if last else None,
            "last_failure": failure.to_dict() if failure else None,
        }

    async def start(self, kind: str, priority: str, created_by: Optional[UUID]) -> Backup:
        if not pg_dump_available():
            raise AppError(503, "pg_dump no esta disponible en el servidor (configura PG_DUMP_PATH)")
        if self._lock.locked():
            raise ConflictError("Ya hay un backup en ejecucion")
        await self._lock.acquire()
        try:
            async with transaction() as conn:
                if await backupRepository.is_running(conn):
                    raise ConflictError("Ya hay un backup en ejecucion")
                tables = await backupRepository.tables(conn)
                backup_id = await backupRepository.create(conn, kind, tables, priority, created_by)
        except BaseException:
            self._lock.release()
            raise

        task = asyncio.create_task(self._run(backup_id, kind))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return await self.get_by_id(backup_id)

    async def _run(self, backup_id: UUID, kind: str) -> None:
        try:
            file_name = f"gestasys-{datetime.now():%Y%m%d-%H%M%S}-{kind}.dump"
            path = backup_dir() / file_name
            status, size, error_text = "completed", None, None
            try:
                await self._dump(path)
                size = path.stat().st_size
                logger.info(f"Backup completado: {file_name}")
            except Exception as err:
                status, error_text, file_name = "failed", str(err)[:500], None
                path.unlink(missing_ok=True)
                logger.error(f"Backup fallido: {err}")
            try:
                async with transaction() as conn:
                    await backupRepository.finish(conn, backup_id, status, file_name, size, error_text)
            except Exception as err:
                logger.error(f"No se pudo actualizar el estado del backup {backup_id}: {err}")
            if status == "completed" and kind == "automatic":
                try:
                    await self._prune()
                except Exception as err:
                    logger.error(f"No se pudieron depurar backups antiguos: {err}")
        finally:
            self._lock.release()

    async def _dump(self, path: Path) -> None:
        backup_dir().mkdir(parents=True, exist_ok=True)
        user, password = config.admin_credentials()
        env = {**os.environ, "PGPASSWORD": password or "", "PGCONNECT_TIMEOUT": "10"}
        process = await asyncio.create_subprocess_exec(
            config.pg_dump_path,
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--host", config.dbhost,
            "--port", str(config.dbport),
            "--username", user,
            "--dbname", config.dbname,
            "--file", str(path),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), DUMP_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            process.kill()
            raise RuntimeError("pg_dump excedio el tiempo maximo")
        if process.returncode != 0:
            detail = output.decode(errors="replace").strip()[:500] or f"codigo de salida {process.returncode}"
            raise RuntimeError(f"pg_dump: {detail}")

    def file_path(self, backup: Backup) -> Path:
        if backup.status != "completed" or not backup.file_name:
            raise ConflictError("El backup no tiene un archivo disponible")
        base = backup_dir()
        path = (base / Path(backup.file_name).name).resolve()
        if path.parent != base:
            raise BadRequestError("Ruta de backup invalida")
        if not path.is_file():
            raise NotFoundError("El archivo del backup ya no existe en el servidor")
        return path

    async def _remove(self, backup: Backup) -> None:
        if backup.file_name:
            try:
                self.file_path(backup).unlink(missing_ok=True)
            except AppError:
                pass
        async with transaction() as conn:
            await backupRepository.delete(conn, backup.id)

    async def delete(self, backup_id: UUID) -> None:
        backup = await self.get_by_id(backup_id)
        if backup.status == "running":
            raise ConflictError("No se puede eliminar un backup en ejecucion")
        await self._remove(backup)

    async def _prune(self) -> None:
        if config.backup_keep <= 0:
            return
        async with connection() as conn:
            old = await backupRepository.old_automatic(conn, config.backup_keep)
        for backup in old:
            await self._remove(backup)

    async def mark_interrupted(self) -> None:
        async with transaction() as conn:
            await backupRepository.mark_interrupted(conn)

    async def _scheduler_loop(self) -> None:
        while True:
            run_at = next_run()
            logger.info(f"Proximo backup automatico: {run_at.isoformat()}")
            await asyncio.sleep(max(1.0, (run_at - datetime.now().astimezone()).total_seconds()))
            try:
                await self.start("automatic", "high", None)
            except Exception as err:
                msg = err.msg if isinstance(err, AppError) else str(err)
                logger.error(f"No se pudo iniciar el backup automatico: {msg}")

    def start_scheduler(self) -> None:
        if not config.backup_auto:
            logger.info("Backups automaticos desactivados (BACKUP_AUTO=false)")
            return
        self._scheduler = asyncio.create_task(self._scheduler_loop())

    async def stop(self) -> None:
        if self._scheduler:
            self._scheduler.cancel()
        for task in list(self._tasks):
            task.cancel()


backupService = BackupService()
