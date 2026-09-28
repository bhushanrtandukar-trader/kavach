"""Exceptions raised by the service layer.  Messages are safe to show to users."""


class AppError(Exception):
    pass


class AuthError(AppError):
    """Wrong username/password (deliberately does not say which)."""

    def __init__(self, message='Invalid username or password.'):
        super().__init__(message)


class LockedOut(AppError):
    def __init__(self, remaining):
        super().__init__(f'Too many failed attempts. Try again in {remaining}s.')
        self.remaining = remaining


class SessionExpired(AppError):
    def __init__(self, message='Your session has expired. Please sign in again.'):
        super().__init__(message)


class Forbidden(AppError):
    def __init__(self, message='You do not have permission to do that.'):
        super().__init__(message)


class NotFound(AppError):
    def __init__(self, message='Not found.'):
        super().__init__(message)


class ValidationError(AppError):
    pass


class Conflict(AppError):
    pass
