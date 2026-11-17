from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.middleware.csrf import CsrfViewMiddleware
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.authentication import SessionAuth
from common.contract import inputs
from common.errors import APIError


def require_user(request):
    from allauth.account.models import EmailAddress

    if not request.user.is_authenticated:
        raise APIError("authentication_required", "Authentication required.", 401)
    if (
        not request.user.is_active
        or not EmailAddress.objects.filter(user=request.user, verified=True).exists()
    ):
        raise APIError("email_unverified", "Verified email required.", 403)
    return request.user


class ContractView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [SessionAuth]
    contract_path = ""
    handlers = {}
    schema = None  # Served by ContractSchemaGenerator, preserving reviewed shapes.

    def execute(self, request, **kwargs):
        from catalog.client import start_budget

        start_budget()
        method = request.method.lower()
        if method == "head":
            method = "get"
        if method not in self.handlers:
            return self.http_method_not_allowed(request)
        if (
            request.path.endswith("guest-sync/")
            and int(request.META.get("CONTENT_LENGTH") or 0) > 1048576
        ):
            raise APIError("payload_too_large", "Synchronization payload exceeds 1 MiB.", 413)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            # DRF normally only CSRF-checks authenticated sessions. Guest writes need it too.
            checker = CsrfViewMiddleware(lambda req: None)
            checker.process_request(request._request)
            denial = checker.process_view(request._request, lambda req: None, (), {})
            if denial:
                raise APIError("permission_denied", "CSRF verification failed.", 403)
        operation, params, data = inputs(request, self.contract_path, method, kwargs)
        if operation.get("security"):
            require_user(request)
        self.rate_limit(request, data)
        try:
            result = self.handlers[method](request, params, data)
        except ValidationError:
            raise APIError("validation_error", "Invalid request.") from None
        return result if isinstance(result, Response) else Response(result)

    def rate_limit(self, request, data):
        import hashlib

        if not settings.API_THROTTLING_ENABLED:
            return
        authenticated = request.user.is_authenticated
        identity = (
            str(request.user.pk) if authenticated else request.META.get("REMOTE_ADDR", "unknown")
        )
        limit = 60
        scope = "read" if request.method in ("GET", "HEAD") else "write"
        if "/auth/" in request.path:
            scope, limit = "auth", 5
        elif "guest-sync" in request.path:
            scope, limit = "sync", 5
        elif "recommendations" in request.path:
            scope, limit = "recommend", 30 if authenticated else 10
        elif "/shared/" in request.path:
            scope, limit = "share", 30
        keys = [identity]
        if scope == "auth" and data.get("email"):
            keys.append(data["email"].strip().casefold())
        for identity in keys:
            digest = hashlib.sha256(identity.encode()).hexdigest()
            key = f"throttle:{scope}:{int(timezone.now().timestamp()) // 60}:{digest}"
            if cache.add(key, 1, 65):
                count = 1
            else:
                try:
                    count = cache.incr(key)
                except ValueError:
                    count = 1
            if count > limit:
                raise APIError("rate_limited", "Too many requests.", 429, retry_after=60)

    get = post = put = patch = delete = execute


def endpoint(path, **handlers):
    """A thin DRF boundary; feature modules supply service handlers."""
    name = "".join(c for c in path.title() if c.isalnum()) + "View"
    return type(
        name,
        (ContractView,),
        {
            "contract_path": path,
            "handlers": handlers,
            "http_method_names": [*handlers, "head", "options"],
        },
    ).as_view()
