# FILE PURPOSE: Runs around each request: adds a request ID and prevents private-response
# caching.
# Import uuid so the code below can use that module namespace.
import uuid

# Import JsonResponse from django.http (Django framework/database/security helpers).
from django.http import JsonResponse


class RequestMiddleware:
    # Remember the next request handler that this middleware must call.
    def __init__(self, get_response):
        # INPUTS TO THIS FUNCTION: self = this class instance; get_response = argument supplied by
        # the caller.
        # Set self.get_response: reuse get_response, which was prepared earlier in this function.
        self.get_response = get_response

    # Run the next handler, then attach request tracing and private-response cache headers.
    def __call__(self, request):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context.
        # Set request.request_id: read uuid.uuid4().hex from the indicated object.
        request.request_id = uuid.uuid4().hex
        # response holds the response produced by the next handler or external HTTP request. Next,
        # call self.get_response with the inputs shown; its definition explains the checks, side
        # effects and return value.
        response = self.get_response(request)
        # Set response['X-Request-ID']: read request.request_id from the indicated object.
        response["X-Request-ID"] = request.request_id
        # Enter this branch only when request.path.startswith(('/api/v1/auth/', '/api/v1/me/',
        # '/api/v1/shared/', '/accounts/')). Otherwise execution uses its alternative or continues
        # below.
        if request.path.startswith(
            ("/api/v1/auth/", "/api/v1/me/", "/api/v1/shared/", "/accounts/")
        ):
            # Set response['Cache-Control']: use the fixed value 'private, no-store'.
            response["Cache-Control"] = "private, no-store"
            # Set response['Referrer-Policy']: use the fixed value 'no-referrer'.
            response["Referrer-Policy"] = "no-referrer"
        # Return the result to the caller: reuse response, which was prepared earlier in this
        # function.
        return response


# Return a JSON explanation when Django rejects the browser CSRF check.
def csrf_failure(request, reason=""):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; reason = argument supplied
    # by the caller.
    # Return the result to the caller: call JsonResponse with the inputs shown; its definition
    # explains the checks, side effects and return value.
    return JsonResponse(
        {
            "error": {
                "code": "permission_denied",
                "message": "CSRF verification failed.",
                "fields": {},
                "request_id": getattr(request, "request_id", ""),
            }
        },
        status=403,
    )
