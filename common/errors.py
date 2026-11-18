# FILE PURPOSE: Turns expected and unexpected API failures into one safe JSON error format.
# Import RequestDataTooBig from django.core.exceptions (Django framework/database/security
# helpers).
from django.core.exceptions import RequestDataTooBig

# Import DatabaseError, IntegrityError from django.db (Django framework/database/security
# helpers).
from django.db import DatabaseError, IntegrityError

# Import APIException from rest_framework.exceptions (DRF request/response helpers).
from rest_framework.exceptions import APIException

# Import Response from rest_framework.response (DRF request/response helpers).
from rest_framework.response import Response


# An expected API failure with a safe code/message/status; services raise this instead of
# returning raw exceptions.
class APIError(APIException):
    # Store the safe public error information; the exception handler formats the HTTP response.
    def __init__(self, code, message, status=400, fields=None, retry_after=None):
        # INPUTS TO THIS FUNCTION: self = this class instance; code = argument supplied by the
        # caller; message = argument supplied by the caller; status = argument supplied by the
        # caller; fields = argument supplied by the caller; retry_after = argument supplied by the
        # caller.
        # Set self.status_code: reuse status, which was prepared earlier in this function.
        self.status_code = status
        # Set self.code: reuse code, which was prepared earlier in this function.
        self.code = code
        # Set self.message: reuse message, which was prepared earlier in this function.
        self.message = message
        # Set self.fields: evaluate fields or {}.
        self.fields = fields or {}
        # Set self.retry_after: reuse retry_after, which was prepared earlier in this function.
        self.retry_after = retry_after
        # Call super().__init__ with the inputs shown; its definition explains the checks, side
        # effects and return value.
        super().__init__(message, code)


# Create the agreed error object, including its status, field messages and request ID.
def error_response(code, message, status, request_id="", fields=None):
    # INPUTS TO THIS FUNCTION: code = argument supplied by the caller; message = argument supplied
    # by the caller; status = argument supplied by the caller; request_id = argument supplied by
    # the caller; fields = argument supplied by the caller.
    # Return the result to the caller: call Response with the inputs shown; its definition
    # explains the checks, side effects and return value.
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


# Translate exceptions into safe API responses; never send a raw traceback or database error to
# React.
def handler(exc, context):
    # INPUTS TO THIS FUNCTION: exc = argument supplied by the caller; context = argument supplied
    # by the caller.
    # Import exception_handler from rest_framework.views (DRF request/response helpers).
    from rest_framework.views import exception_handler

    # Set request: look up a named setting/value or make the indicated GET call; the surrounding
    # object determines which.
    request = context.get("request")
    # Set request_id: call getattr with the inputs shown; its definition explains the checks, side
    # effects and return value.
    request_id = getattr(request, "request_id", "")
    if isinstance(exc, RecursionError):
        return error_response("validation_error", "Request nesting is too deep.", 400, request_id)
    # Enter this branch only when isinstance(exc, RequestDataTooBig). Otherwise execution uses its
    # alternative or continues below.
    if isinstance(exc, RequestDataTooBig):
        # Return the result to the caller: call error_response with the inputs shown; its
        # definition explains the checks, side effects and return value.
        return error_response("payload_too_large", "Request exceeds 1 MiB.", 413, request_id)
    # Enter this branch only when isinstance(exc, APIError). Otherwise execution uses its
    # alternative or continues below.
    if isinstance(exc, APIError):
        # response holds the response produced by the next handler or external HTTP request. Next,
        # call error_response with the inputs shown; its definition explains the checks, side
        # effects and return value.
        response = error_response(exc.code, exc.message, exc.status_code, request_id, exc.fields)
        # Enter this branch only when exc.retry_after. Otherwise execution uses its alternative or
        # continues below.
        if exc.retry_after:
            # Set response['Retry-After']: convert this value to text for an identifier, URL or
            # response field.
            response["Retry-After"] = str(exc.retry_after)
        # Return the result to the caller: reuse response, which was prepared earlier in this
        # function.
        return response
    # Enter this branch only when isinstance(exc, IntegrityError). Otherwise execution uses its
    # alternative or continues below.
    if isinstance(exc, IntegrityError):
        # Return the result to the caller: call error_response with the inputs shown; its
        # definition explains the checks, side effects and return value.
        return error_response("conflict", "Conflicting data.", 409, request_id)
    # Enter this branch only when isinstance(exc, DatabaseError). Otherwise execution uses its
    # alternative or continues below.
    if isinstance(exc, DatabaseError):
        # Return the result to the caller: call error_response with the inputs shown; its
        # definition explains the checks, side effects and return value.
        return error_response(
            "service_unavailable", "Database temporarily unavailable.", 503, request_id
        )
    # response holds the response produced by the next handler or external HTTP request. Next,
    # call exception_handler with the inputs shown; its definition explains the checks, side
    # effects and return value.
    response = exception_handler(exc, context)
    # Enter this branch only when response is None. Otherwise execution uses its alternative or
    # continues below.
    if response is None:
        # Never serialize the exception string or upstream response.
        # Import logging so the code below can use that module namespace.
        import logging

        # Call logging.getlogger(__name__).error with the inputs shown; its definition explains
        # the checks, side effects and return value.
        logging.getLogger(__name__).error(
            "Unhandled API failure request_id=%s type=%s", request_id, type(exc).__name__
        )
        # Return the result to the caller: call error_response with the inputs shown; its
        # definition explains the checks, side effects and return value.
        return error_response("internal_error", "An internal error occurred.", 500, request_id)
    # codes holds supported language codes collected into a set for fast membership checks. Next,
    # build a dictionary with named fields such as 400, 401, 403, 404, 405, 415, 429.
    codes = {
        400: "validation_error",
        401: "authentication_required",
        403: "permission_denied",
        404: "not_found",
        405: "method_not_allowed",
        415: "unsupported_media_type",
        429: "rate_limited",
    }
    # fields holds the safe field-to-message mapping that the browser can display. Next, choose
    # response.data when response.status_code == 400 and isinstance(response.data, dict);
    # otherwise use {}.
    fields = (
        response.data if response.status_code == 400 and isinstance(response.data, dict) else {}
    )
    # Set message: look up a named setting/value or make the indicated GET call; the surrounding
    # object determines which.
    message = {
        400: "Invalid request.",
        401: "Authentication required.",
        403: "Permission denied.",
        404: "Not found.",
        429: "Too many requests.",
    }.get(response.status_code, "Request rejected.")
    # Set result: call error_response with the inputs shown; its definition explains the checks,
    # side effects and return value.
    result = error_response(
        codes.get(response.status_code, "request_error"),
        message,
        response.status_code,
        request_id,
        fields,
    )
    # Enter this branch only when response.has_header('Retry-After'). Otherwise execution uses its
    # alternative or continues below.
    if response.has_header("Retry-After"):
        # Set result['Retry-After']: read the entry indexed by 'Retry-After' from response.
        result["Retry-After"] = response["Retry-After"]
    # Return the result to the caller: reuse result, which was prepared earlier in this function.
    return result
