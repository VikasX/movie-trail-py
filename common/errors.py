from django.core.exceptions import RequestDataTooBig
from django.db import DatabaseError, IntegrityError
from rest_framework.exceptions import APIException
from rest_framework.response import Response


class APIError(APIException):
    def __init__(self, code, message, status=400, fields=None, retry_after=None):
        self.status_code = status
        self.code = code
        self.message = message
        self.fields = fields or {}
        self.retry_after = retry_after
        super().__init__(message, code)


def error_response(code, message, status, request_id="", fields=None):
    return Response(
        {
            "error": {
                "code": code,
                "message": message,
                "fields": fields or {},
                "request_id": request_id,
            }
        },
        status=status,
    )


def handler(exc, context):
    from rest_framework.views import exception_handler

    request = context.get("request")
    request_id = getattr(request, "request_id", "")
    if isinstance(exc, RequestDataTooBig):
        return error_response("payload_too_large", "Request exceeds 1 MiB.", 413, request_id)
    if isinstance(exc, APIError):
        response = error_response(exc.code, exc.message, exc.status_code, request_id, exc.fields)
        if exc.retry_after:
            response["Retry-After"] = str(exc.retry_after)
        return response
    if isinstance(exc, IntegrityError):
        return error_response("conflict", "Conflicting data.", 409, request_id)
    if isinstance(exc, DatabaseError):
        return error_response(
            "service_unavailable", "Database temporarily unavailable.", 503, request_id
        )
    response = exception_handler(exc, context)
    if response is None:
        # Never serialize the exception string or upstream response.
        import logging

        logging.getLogger(__name__).error(
            "Unhandled API failure request_id=%s type=%s", request_id, type(exc).__name__
        )
        return error_response("internal_error", "An internal error occurred.", 500, request_id)
    codes = {
        400: "validation_error",
        401: "authentication_required",
        403: "permission_denied",
        404: "not_found",
        405: "method_not_allowed",
        415: "unsupported_media_type",
        429: "rate_limited",
    }
    fields = (
        response.data if response.status_code == 400 and isinstance(response.data, dict) else {}
    )
    message = {
        400: "Invalid request.",
        401: "Authentication required.",
        403: "Permission denied.",
        404: "Not found.",
        429: "Too many requests.",
    }.get(response.status_code, "Request rejected.")
    result = error_response(
        codes.get(response.status_code, "request_error"),
        message,
        response.status_code,
        request_id,
        fields,
    )
    if response.has_header("Retry-After"):
        result["Retry-After"] = response["Retry-After"]
    return result
