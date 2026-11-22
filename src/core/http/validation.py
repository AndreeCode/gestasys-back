import re
from datetime import date

from email_validator import EmailNotValidError, validate_email

from ..security.common_passwords import COMMON_PASSWORDS
from .app_error import ValidationError

DNI_RE = re.compile(r"^[0-9]{8}$")


class Validator:
    def __init__(self):
        self.errors: list[str] = []

    def add(self, msg: str) -> None:
        self.errors.append(msg)

    def check(self, ok: bool, msg: str) -> None:
        if not ok:
            self.errors.append(msg)

    def required(self, field: str, value: str | None) -> None:
        self.check(bool(value and value.strip()), f"{field} es obligatorio")

    def max_len(self, field: str, value: str | None, n: int) -> None:
        if value is not None:
            self.check(len(value) <= n, f"{field} no debe superar {n} caracteres")

    def dni(self, field: str, value: str | None) -> None:
        if value:
            self.check(bool(DNI_RE.match(value)), f"{field} debe tener 8 digitos")

    def email(self, field: str, value: str | None) -> None:
        if not value:
            return
        try:
            validate_email(value, check_deliverability=False)
        except EmailNotValidError:
            self.add(f"{field} no es un correo valido")

    def password(self, field: str, value: str | None) -> None:
        value = value or ""
        if len(value) < 8:
            self.add(f"{field} debe tener al menos 8 caracteres")
            return
        self.check(len(value) <= 128, f"{field} no debe superar 128 caracteres")
        self.check(
            any(c.isdigit() for c in value) and any(c.isalpha() for c in value),
            f"{field} debe combinar letras y numeros",
        )
        lowered = value.lower()
        self.check(
            lowered not in COMMON_PASSWORDS and lowered.rstrip("!.*#$@") not in COMMON_PASSWORDS,
            f"{field} es demasiado comun, elige otra",
        )

    def one_of(self, field: str, value: str | None, allowed: list[str] | tuple[str, ...]) -> None:
        self.check(value in allowed, f"{field} debe ser uno de: {', '.join(allowed)}")

    def between(self, field: str, value, lo, hi) -> None:
        if value is not None:
            self.check(lo <= value <= hi, f"{field} debe estar entre {lo} y {hi}")

    def raise_if_errors(self) -> None:
        if self.errors:
            raise ValidationError(self.errors)


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


def age_on(birth: date, today: date) -> int:
    years = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        years -= 1
    return years
