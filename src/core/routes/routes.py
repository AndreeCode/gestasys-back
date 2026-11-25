from fastapi import APIRouter

from ...modules.audit_log.audit_log_route import router as audit_log_router
from ...modules.auth.auth_route import router as auth_router
from ...modules.backup.backup_route import router as backup_router
from ...modules.dashboard.dashboard_route import router as dashboard_router
from ...modules.data_import.data_import_route import router as data_import_router
from ...modules.device.device_route import router as device_router
from ...modules.health_facility.health_facility_route import router as health_facility_router
from ...modules.micro_network.micro_network_route import router as micro_network_router
from ...modules.permission.permission_route import router as permission_router
from ...modules.pregnancy.pregnancy_route import router as pregnancy_router
from ...modules.prenatal_control.prenatal_control_route import router as prenatal_control_router
from ...modules.role.role_route import router as role_router
from ...modules.session.session_route import router as session_router
from ...modules.user.user_route import router as user_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(dashboard_router)
router.include_router(user_router)
router.include_router(role_router)
router.include_router(permission_router)
router.include_router(micro_network_router)
router.include_router(health_facility_router)
router.include_router(pregnancy_router)
router.include_router(prenatal_control_router)
router.include_router(data_import_router)
router.include_router(backup_router)
router.include_router(device_router)
router.include_router(session_router)
router.include_router(audit_log_router)
