# FILE PURPOSE: Shared DRF request checkpoint. It validates, checks security and dispatches to a
# feature service.
# LEARNING TIP: read the matching walkthrough in docs/BACKEND_GUIDE.md, then follow the block
# comments below.
# Import settings from django.conf (Django framework/database/security helpers).
from django.conf import settings

# Import cache from django.core.cache (Django framework/database/security helpers).
from django.core.cache import cache

# Import ValidationError from django.core.exceptions (Django framework/database/security helpers).
from django.core.exceptions import ValidationError

# Import CsrfViewMiddleware from django.middleware.csrf (Django framework/database/security
# helpers).
from django.middleware.csrf import CsrfViewMiddleware

# Import timezone from django.utils (Django framework/database/security helpers).
from django.utils import timezone

# Import AllowAny from rest_framework.permissions (DRF request/response helpers).
from rest_framework.permissions import AllowAny

# Import Response from rest_framework.response (DRF request/response helpers).
from rest_framework.response import Response

# Import APIView from rest_framework.views (DRF request/response helpers).
from rest_framework.views import APIView

# Import SessionAuth from common.authentication (our shared API layer).
from common.authentication import SessionAuth

# Import inputs from common.contract (our shared API layer).
from common.contract import inputs

# Import APIError from common.errors (our shared API layer).
from common.errors import APIError


# Require a signed-in, active account with a verified email before allowing a private action.
def require_user(request):
    # INPUTS TO THIS FUNCTION: request = current browser/user context.
    # Import EmailAddress from allauth.account.models (the maintained account/Google integration).
    from allauth.account.models import EmailAddress

    # Stop anonymous access here; a public URL elsewhere does not grant account access.
    if not request.user.is_authenticated:
        # Stop this action with safe API error 'authentication_required' (HTTP 401). The common
        # handler builds its JSON envelope.
        raise APIError("authentication_required", "Authentication required.", 401)
    # Enter this branch only when not request.user.is_active or not
    # EmailAddress.objects.filter(user=request.user, verified=True).exists(). Otherwise execution
    # uses its alternative or continues below.
    if (
        not request.user.is_active
        or not EmailAddress.objects.filter(user=request.user, verified=True).exists()
    ):
        # Stop this action with safe API error 'email_unverified' (HTTP 403). The common handler
        # builds its JSON envelope.
        raise APIError("email_unverified", "Verified email required.", 403)
    # Return the result to the caller: read request.user from the indicated object.
    return request.user


# One shared request pipeline for many endpoints. Permission decisions come from each operation
# contract.
class ContractView(APIView):
    # Set permission_classes: build an ordered list of 1 entries.
    permission_classes = [AllowAny]
    # Set authentication_classes: build an ordered list of 1 entries.
    authentication_classes = [SessionAuth]
    # Set contract_path: use the fixed value ''.
    contract_path = ""
    # Set handlers: build a dictionary with named fields.
    handlers = {}
    # Set schema: use None to represent no known value (JSON null at the API boundary).
    schema = None  # Served by ContractSchemaGenerator, preserving reviewed shapes.

    # Follow the same request checklist for every product endpoint before calling its feature
    # function.
    def execute(self, request, **kwargs):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context.
        # Import start_budget from catalog.client (our TMDB/normalization layer).
        from catalog.client import start_budget

        # Reset the external-request allowance before this endpoint performs any TMDB work.
        # Call start_budget with the inputs shown; its definition explains the checks, side
        # effects and return value.
        start_budget()
        # Translate GET to get, POST to post, etc., because handler dictionary keys use lowercase
        # names.
        method = request.method.lower()
        # Enter this branch only when method == 'head'. Otherwise execution uses its alternative
        # or continues below.
        if method == "head":
            # method holds the HTTP method in lowercase, used to select the matching feature
            # handler. Next, use the fixed value 'get'.
            method = "get"
        # Enter this branch only when method not in self.handlers. Otherwise execution uses its
        # alternative or continues below.
        if method not in self.handlers:
            # Return the result to the caller: call self.http_method_not_allowed with the inputs
            # shown; its definition explains the checks, side effects and return value.
            return self.http_method_not_allowed(request)
        # Enter this branch only when request.path.endswith('guest-sync/') and
        # int(request.META.get('CONTENT_LENGTH') or 0) > 1048576. Otherwise execution uses its
        # alternative or continues below.
        if (
            request.path.endswith("guest-sync/")
            and int(request.META.get("CONTENT_LENGTH") or 0) > 1048576
        ):
            # Stop this action with safe API error 'payload_too_large' (HTTP 413). The common
            # handler builds its JSON envelope.
            raise APIError("payload_too_large", "Synchronization payload exceeds 1 MiB.", 413)
        # Enter this branch only when request.method not in ('GET', 'HEAD', 'OPTIONS'). Otherwise
        # execution uses its alternative or continues below.
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            # DRF normally only CSRF-checks authenticated sessions. Guest writes need it too.
            # checker holds Django CSRF middleware used explicitly for this product request. Next,
            # call CsrfViewMiddleware with the inputs shown; its definition explains the checks,
            # side effects and return value.
            checker = CsrfViewMiddleware(lambda req: None)
            # Read the CSRF cookie from the original Django request. request._request unwraps DRF
            # request handling.
            checker.process_request(request._request)
            # Ask Django to compare cookie/header and Origin/Referer. A rejection stops the
            # service call below.
            denial = checker.process_view(request._request, lambda req: None, (), {})
            # Enter this branch only when denial. Otherwise execution uses its alternative or
            # continues below.
            if denial:
                # Stop this action with safe API error 'permission_denied' (HTTP 403). The common
                # handler builds its JSON envelope.
                raise APIError("permission_denied", "CSRF verification failed.", 403)
        # Read the matched operation and get cleaned URL/query parameters plus validated JSON.
        # Set (operation, params, data): call inputs with the inputs shown; its definition
        # explains the checks, side effects and return value.
        operation, params, data = inputs(request, self.contract_path, method, kwargs)
        # AllowAny above lets public routes enter; this per-operation check still protects
        # private routes.
        # Enter this branch only when operation.get('security'). Otherwise execution uses its
        # alternative or continues below.
        if operation.get("security"):
            # Call require_user with the inputs shown; its definition explains the checks, side
            # effects and return value.
            require_user(request)
        # Apply our own per-client throttle before executing the feature; this is separate from
        # TMDB upstream throttling.
        self.rate_limit(request, data)
        # Attempt this block; the following except branches handle expected failures without
        # continuing the success path.
        try:
            # This is the handoff to the actual feature; handlers is a dictionary such as {get:
            # discover}.
            # Set result: call self.handlers[method] with the inputs shown; its definition
            # explains the checks, side effects and return value.
            result = self.handlers[method](request, params, data)
        # Handle ValidationError here. The original exception is not automatically safe to expose
        # to the client.
        except ValidationError:
            # Stop this action with safe API error 'validation_error' (HTTP 400). The common
            # handler builds its JSON envelope.
            raise APIError("validation_error", "Invalid request.") from None
        # Return the result to the caller: choose result when isinstance(result, Response);
        # otherwise use Response(result).
        return result if isinstance(result, Response) else Response(result)

    # Count recent requests by account/IP and sometimes email; reject bursts with HTTP 429.
    def rate_limit(self, request, data):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context; data = validated JSON.
        # Import hashlib so the code below can use that module namespace.
        import hashlib

        # Enter this branch only when not settings.API_THROTTLING_ENABLED. Otherwise execution
        # uses its alternative or continues below.
        if not settings.API_THROTTLING_ENABLED:
            # Exit this function now without a result; no remaining statements in this function
            # run.
            return
        # authenticated holds whether Django recognized a signed-in user for this request. Next,
        # read request.user.is_authenticated from the indicated object.
        authenticated = request.user.is_authenticated
        # identity holds the account/IP value used for counting requests, or the composite title
        # pair in library helpers. Next, choose str(request.user.pk) when authenticated; otherwise
        # use request.META.get('REMOTE_ADDR', 'unknown').
        identity = (
            str(request.user.pk) if authenticated else request.META.get("REMOTE_ADDR", "unknown")
        )
        # limit holds the cap chosen for this operation: request rate, page/candidate count, or
        # recommendations. Next, use the fixed value 60.
        limit = 60
        # scope holds the counter category so login bursts and ordinary reading do not share one
        # bucket. Next, choose 'read' when request.method in ('GET', 'HEAD'); otherwise use
        # 'write'.
        scope = "read" if request.method in ("GET", "HEAD") else "write"
        # Enter this branch only when '/auth/' in request.path. Otherwise execution uses its
        # alternative or continues below.
        if "/auth/" in request.path:
            # Set (scope, limit): keep these related values together as a tuple: 'auth', 5.
            scope, limit = "auth", 5
        # Enter this branch only when 'guest-sync' in request.path. Otherwise execution uses its
        # alternative or continues below.
        elif "guest-sync" in request.path:
            # Set (scope, limit): keep these related values together as a tuple: 'sync', 5.
            scope, limit = "sync", 5
        # Enter this branch only when 'recommendations' in request.path. Otherwise execution uses
        # its alternative or continues below.
        elif "recommendations" in request.path:
            # Set (scope, limit): keep these related values together as a tuple: 'recommend', 30
            # if authenticated else 10.
            scope, limit = "recommend", 30 if authenticated else 10
        # Enter this branch only when '/shared/' in request.path. Otherwise execution uses its
        # alternative or continues below.
        elif "/shared/" in request.path:
            # Set (scope, limit): keep these related values together as a tuple: 'share', 30.
            scope, limit = "share", 30
        # Set keys: build an ordered list of 1 entries.
        keys = [identity]
        # Enter this branch only when scope == 'auth' and data.get('email'). Otherwise execution
        # uses its alternative or continues below.
        if scope == "auth" and data.get("email"):
            # Add one item at the end of this list.
            keys.append(data["email"].strip().casefold())
        # Repeat the following block for each identity from keys. Each iteration handles that one
        # item/pair.
        for identity in keys:
            # digest holds a one-way fingerprint used in a lookup key instead of storing the
            # original value in that key. Next, represent a hash as printable hexadecimal text;
            # this does not reveal its original secret.
            digest = hashlib.sha256(identity.encode()).hexdigest()
            # Set key: evaluate f'throttle:{scope}:{int(timezone.now().timestamp()) //
            # 60}:{digest}'.
            key = f"throttle:{scope}:{int(timezone.now().timestamp()) // 60}:{digest}"
            # Enter this branch only when cache.add(key, 1, 65). Otherwise execution uses its
            # alternative or continues below.
            if cache.add(key, 1, 65):
                # count holds the current list length or request counter; it does not mean the
                # full size of TMDB. Next, use the fixed value 1.
                count = 1
            else:
                # Attempt this block; the following except branches handle expected failures
                # without continuing the success path.
                try:
                    # count holds the current list length or request counter; it does not mean the
                    # full size of TMDB. Next, increase the existing cache counter.
                    count = cache.incr(key)
                # Handle ValueError here. The original exception is not automatically safe to
                # expose to the client.
                except ValueError:
                    # count holds the current list length or request counter; it does not mean the
                    # full size of TMDB. Next, use the fixed value 1.
                    count = 1
            # Enter this branch only when count > limit. Otherwise execution uses its alternative
            # or continues below.
            if count > limit:
                # Stop this action with safe API error 'rate_limited' (HTTP 429). The common
                # handler builds its JSON envelope.
                raise APIError("rate_limited", "Too many requests.", 429, retry_after=60)

    # DRF selects a method name; every supported method intentionally enters the same checklist.
    # Set get, post, put, patch, delete: reuse execute, which was prepared earlier in this
    # function.
    get = post = put = patch = delete = execute


# Build a small view class from a URL contract and its GET/POST/etc. service functions.
def endpoint(path, **handlers):
    """A thin DRF boundary; feature modules supply service handlers."""
    # INPUTS TO THIS FUNCTION: path = argument supplied by the caller.
    # name holds a display name or field label; collection names are trimmed and checked for
    # allowed length. Next, calculate ''.join((c for c in path.title() if c.isalnum())) + 'View'
    # from the intermediate values already prepared.
    name = "".join(c for c in path.title() if c.isalnum()) + "View"
    # Return the result to the caller: call type(name, (ContractView,), {'contract_path': path,
    # 'handlers': handlers, 'http_method_names': [*handlers, 'head', 'options']}).as_view with the
    # inputs shown; its definition explains the checks, side effects and return value.
    return type(
        name,
        (ContractView,),
        {
            "contract_path": path,
            "handlers": handlers,
            "http_method_names": [*handlers, "head", "options"],
        },
    ).as_view()
