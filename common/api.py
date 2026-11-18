# FILE PURPOSE: Shared DRF request checkpoint. It validates, checks security and dispatches to a
# feature service.
# LEARNING TIP: read the matching walkthrough in docs/BACKEND_GUIDE.md, then follow the block
# comments below.


# Import ValidationError from django.core.exceptions (Django framework/database/security helpers).
from django.core.exceptions import ValidationError

# Import CsrfViewMiddleware from django.middleware.csrf (Django framework/database/security
# helpers).
from django.middleware.csrf import CsrfViewMiddleware

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
from common.throttling import email_limit, request_limit


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
        # Apply the shared limit before parsing/validating attacker-controlled payloads.
        request_limit(request)
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
        # Add a normalized-email limit after schema validation, before any password hash or mail.
        email_limit(request, data)
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
