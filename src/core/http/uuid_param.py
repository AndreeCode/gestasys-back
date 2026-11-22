from uuid import UUID

from .app_error import BadRequestError


class InvalidUUIDError(BadRequestError):
    pass


def parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(str(value).strip())
    except ValueError:
        raise InvalidUUIDError(f"{field_name} debe ser un UUID valido: {value}")


def parse_optional_uuid(value: str | None, field_name: str) -> UUID | None:
    if value is None or str(value).strip() == "":
        return None
    return parse_uuid(value, field_name)
