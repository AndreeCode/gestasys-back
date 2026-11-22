class AppError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status
        self.msg = msg


class BadRequestError(AppError):
    def __init__(self, msg: str):
        super().__init__(400, msg)


class UnauthorizedError(AppError):
    def __init__(self, msg: str = "No autenticado"):
        super().__init__(401, msg)


class ForbiddenError(AppError):
    def __init__(self, msg: str):
        super().__init__(403, msg)


class NotFoundError(AppError):
    def __init__(self, msg: str):
        super().__init__(404, msg)


class ConflictError(AppError):
    def __init__(self, msg: str):
        super().__init__(409, msg)


class ValidationError(AppError):
    def __init__(self, errors: list[str] | str):
        if isinstance(errors, str):
            errors = [errors]
        super().__init__(422, "; ".join(errors))
        self.errors = errors
