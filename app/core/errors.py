from fastapi import status


class AppError(Exception):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "internal_error"

    def __init__(self, message: str, *, detail: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class RequestPolicyError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "request_policy_violation"

