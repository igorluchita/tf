class TokenExpiredError(Exception):
    """Raised when a remote API indicates the token is invalid or expired."""


__all__ = ["TokenExpiredError"]
