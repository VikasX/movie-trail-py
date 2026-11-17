import uuid

from django.http import JsonResponse


class RequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = uuid.uuid4().hex
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        if request.path.startswith(
            ("/api/v1/auth/", "/api/v1/me/", "/api/v1/shared/", "/accounts/")
        ):
            response["Cache-Control"] = "private, no-store"
            response["Referrer-Policy"] = "no-referrer"
        return response


def csrf_failure(request, reason=""):
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
