PERMISSIONS: dict[str, str] = {
    "dashboard.get": "Ver el resumen general",
    "user.get": "Listar y ver usuarios",
    "user.post": "Registrar usuarios",
    "user.put": "Editar, bloquear y resetear usuarios",
    "user.delete": "Desactivar usuarios",
    "role.get": "Listar y ver roles",
    "role.post": "Crear roles",
    "role.put": "Editar roles y sus permisos",
    "role.delete": "Eliminar roles",
    "permission.get": "Ver el catalogo de permisos",
    "health_facility.get": "Listar establecimientos de salud",
    "health_facility.post": "Crear establecimientos de salud",
    "health_facility.put": "Editar establecimientos de salud",
    "health_facility.delete": "Eliminar establecimientos de salud",
    "pregnancy.get": "Consultar registros de gestantes",
    "pregnancy.post": "Crear registros de gestantes",
    "pregnancy.put": "Editar registros de gestantes",
    "pregnancy.delete": "Eliminar registros de gestantes",
    "pregnancy.import": "Importar registros desde CSV",
    "pregnancy.export": "Exportar registros a CSV",
    "prenatal_control.get": "Consultar controles prenatales",
    "prenatal_control.post": "Registrar controles prenatales",
    "prenatal_control.put": "Editar controles prenatales",
    "prenatal_control.delete": "Eliminar controles prenatales",
    "data_import.get": "Ver el historial de importaciones",
    "backup.get": "Ver y descargar backups",
    "backup.post": "Crear backups manuales",
    "backup.delete": "Eliminar backups",
    "device.get": "Ver dispositivos",
    "device.put": "Bloquear o desbloquear dispositivos",
    "session.get": "Ver sesiones",
    "session.delete": "Cerrar sesiones de otros usuarios",
    "audit_log.get": "Ver la bitacora de auditoria",
}

ADMIN_ROLE = "admin"

SYSTEM_ROLES: list[dict] = [
    {"name": ADMIN_ROLE, "description": "Acceso total", "codes": list(PERMISSIONS)},
    {
        "name": "coordinador",
        "description": "Gestion operativa",
        "codes": [
            "dashboard.get",
            "user.post",
            "health_facility.get",
            "pregnancy.get",
            "pregnancy.post",
            "pregnancy.put",
            "pregnancy.import",
            "pregnancy.export",
            "prenatal_control.get",
            "prenatal_control.post",
            "prenatal_control.put",
            "prenatal_control.delete",
            "data_import.get",
        ],
    },
    {
        "name": "consulta",
        "description": "Solo lectura",
        "codes": [
            "dashboard.get",
            "health_facility.get",
            "pregnancy.get",
            "pregnancy.export",
            "prenatal_control.get",
        ],
    },
]


def module_of(code: str) -> str:
    return code.split(".", 1)[0]
