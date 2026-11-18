# FILE PURPOSE: Account actions: email login, verification, reset, profile and CSRF bootstrap.
# Import hashlib so the code below can use that module namespace.
import hashlib

# Import secrets so the code below can use that module namespace.
import secrets

# Import uuid so the code below can use that module namespace.
import uuid

# Import timedelta from datetime (the named Python helper module).
from datetime import timedelta

# Import urlencode from urllib.parse (the named Python helper module).
from urllib.parse import urlencode

# Import EmailAddress from allauth.account.models (the maintained account/Google integration).
from allauth.account.models import EmailAddress

# Import settings from django.conf (Django framework/database/security helpers).
from django.conf import settings

# Import get_user_model from django.contrib.auth (Django framework/database/security helpers).
from django.contrib.auth import get_user_model

# Import login from django.contrib.auth (Django framework/database/security helpers).
from django.contrib.auth import login as session_login

# Import logout from django.contrib.auth (Django framework/database/security helpers).
from django.contrib.auth import logout as session_logout

# Import validate_password from django.contrib.auth.password_validation (Django
# framework/database/security helpers).
from django.contrib.auth.password_validation import validate_password

# Import ValidationError from django.core.exceptions (Django framework/database/security helpers).
from django.core.exceptions import ValidationError

# Import send_mail from django.core.mail (Django framework/database/security helpers).
from django.core.mail import send_mail

# Import IntegrityError, transaction from django.db (Django framework/database/security helpers).
from django.db import IntegrityError, transaction

# Import get_token from django.middleware.csrf (Django framework/database/security helpers).
from django.middleware.csrf import get_token

# Import timezone from django.utils (Django framework/database/security helpers).
from django.utils import timezone

# Import Response from rest_framework.response (DRF request/response helpers).
from rest_framework.response import Response

# Import AccountToken, UserPreferences from accounts.models (our account layer).
from accounts.models import AccountToken, UserPreferences

# Import APIError from common.errors (our shared API layer).
from common.errors import APIError

# Set User: call get_user_model with the inputs shown; its definition explains the checks, side
# effects and return value.
User = get_user_model()
# Set MESSAGE: build a dictionary with named fields such as detail.
MESSAGE = {"detail": "If eligible, instructions have been sent."}


# Turn a secret token into a one-way hash so the database can look it up without storing the raw
# value.
def digest(token):
    # INPUTS TO THIS FUNCTION: token = argument supplied by the caller.
    # Return the result to the caller: represent a hash as printable hexadecimal text; this does
    # not reveal its original secret.
    return hashlib.sha256(token.encode()).hexdigest()


# Build the public account/profile response without exposing password hashes or provider
# secrets.
def user_data(user):
    # INPUTS TO THIS FUNCTION: user = Django account.
    # pref holds the user preference record, or unsaved default preferences when no record exists.
    # Next, evaluate UserPreferences.objects.filter(user=user).first() or
    # UserPreferences(user=user).
    pref = UserPreferences.objects.filter(user=user).first() or UserPreferences(user=user)
    # providers holds the account connected login methods, without any provider access tokens.
    # Next, call list with the inputs shown; its definition explains the checks, side effects and
    # return value.
    providers = list(user.socialaccount_set.values_list("provider", flat=True))
    # Enter this branch only when user.has_usable_password(). Otherwise execution uses its
    # alternative or continues below.
    if user.has_usable_password():
        # Add one item at the end of this list.
        providers.append("email")
    # Return this named-field dictionary; API handlers turn it into JSON, while helper callers use
    # it directly.
    return {
        "id": user.pk,
        "email": user.email,
        "display_name": pref.display_name,
        # Reports verification state, not merely whether the user typed an email address.
        "email_verified": EmailAddress.objects.filter(user=user, verified=True).exists(),
        # Names of connected login methods. No provider secret/access token belongs in this
        # response.
        "providers": sorted(set(providers)),
        # Language/region choices belonging to this account.
        "preferences": {"language": pref.display_language, "region": pref.region},
    }


# Apply Django password rules and return a helpful generic failure instead of sensitive details.
def password_check(password, user=None):
    # INPUTS TO THIS FUNCTION: password = argument supplied by the caller; user = Django account.
    # Attempt this block; the following except branches handle expected failures without
    # continuing the success path.
    try:
        # Call validate_password with the inputs shown; its definition explains the checks, side
        # effects and return value.
        validate_password(password, user)
    # Handle ValidationError here. The original exception is not automatically safe to expose to
    # the client.
    except ValidationError:
        # Stop this action with safe API error 'validation_error' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError(
            "validation_error",
            "Password does not meet security requirements.",
            fields={"password": ["Use a stronger password."]},
        ) from None


# Check the minimum email configuration before accepting an operation that needs delivery.
def email_ready():
    # Enter this branch only when not settings.FRONTEND_PUBLIC_ORIGIN. Otherwise execution uses
    # its alternative or continues below.
    if not settings.FRONTEND_PUBLIC_ORIGIN:
        # Stop this action with safe API error 'service_unavailable' (HTTP 503). The common
        # handler builds its JSON envelope.
        raise APIError("service_unavailable", "Email delivery is not configured.", 503)
    # Enter this branch only when not settings.DEBUG and ('console' in settings.EMAIL_BACKEND or
    # 'locmem' in settings.EMAIL_BACKEND or ('smtp' in settings.EMAIL_BACKEND and (not
    # settings.EMAIL_HOST))). Otherwise execution uses its alternative or continues below.
    if not settings.DEBUG and (
        "console" in settings.EMAIL_BACKEND
        or "locmem" in settings.EMAIL_BACKEND
        or ("smtp" in settings.EMAIL_BACKEND and not settings.EMAIL_HOST)
    ):
        # Stop this action with safe API error 'service_unavailable' (HTTP 503). The common
        # handler builds its JSON envelope.
        raise APIError("service_unavailable", "Email delivery is not configured.", 503)


# Create a random expiring token, store its hash and email the frontend completion link.
def issue_token(user, purpose):
    # INPUTS TO THIS FUNCTION: user = Django account; purpose = argument supplied by the caller.
    # Set token: generate cryptographically strong random URL-safe text, not a predictable
    # sequence.
    token = secrets.token_urlsafe(48)
    # record holds the database row recording this one-time token lifecycle. Next, insert a new
    # row and receive the created model object.
    record = AccountToken.objects.create(
        user=user,
        purpose=purpose,
        token_hash=digest(token),
        expires_at=timezone.now() + timedelta(hours=24 if purpose == "verify" else 1),
    )
    # path holds the route to request externally or the frontend completion path; read the
    # surrounding function for its role. Next, choose '/auth/verify-email' when purpose ==
    # 'verify'; otherwise use '/auth/reset-password'.
    path = "/auth/verify-email" if purpose == "verify" else "/auth/reset-password"
    # url holds the complete public navigation URL built from the approved configured origin.
    # Next, calculate settings.FRONTEND_PUBLIC_ORIGIN + path + '?' + urlencode({'token': token})
    # from the intermediate values already prepared.
    url = settings.FRONTEND_PUBLIC_ORIGIN + path + "?" + urlencode({"token": token})
    # Attempt this block; the following except branches handle expected failures without
    # continuing the success path.
    try:
        # Call send_mail with the inputs shown; its definition explains the checks, side effects
        # and return value.
        send_mail(
            "CineScope account instructions",
            f"Open this link to continue: {url}",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    # Handle Exception here. The original exception is not automatically safe to expose to the
    # client.
    except Exception:
        # Delete the selected row(s), applying their configured related-row deletion rules.
        record.delete()
        # Stop this action with safe API error 'service_unavailable' (HTTP 503). The common
        # handler builds its JSON envelope.
        raise APIError(
            "service_unavailable", "Email delivery temporarily unavailable.", 503
        ) from None


# Create a pending account when needed and return the same accepted message for an existing
# email.
def register(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # Call email_ready with the inputs shown; its definition explains the checks, side effects and
    # return value.
    email_ready()
    # email holds the trimmed, case-normalized address used for account lookup/uniqueness. Next,
    # call data['email'].strip().casefold with the inputs shown; its definition explains the
    # checks, side effects and return value.
    email = data["email"].strip().casefold()
    # Call password_check with the inputs shown; its definition explains the checks, side effects
    # and return value.
    password_check(data["password"], User(email=email))
    # Enter this branch only when not User.objects.filter(email__iexact=email).exists(). Otherwise
    # execution uses its alternative or continues below.
    if not User.objects.filter(email__iexact=email).exists():
        # Attempt this block; the following except branches handle expected failures without
        # continuing the success path.
        try:
            # Start an atomic write boundary. Leaving normally commits it; an exception rolls back
            # this block changes.
            with transaction.atomic():
                # user holds the Django account involved in this action; do not confuse it with
                # the client-submitted email string. Next, call User.objects.create_user with the
                # inputs shown; its definition explains the checks, side effects and return value.
                user = User.objects.create_user(
                    username=uuid.uuid4().hex, email=email, password=data["password"]
                )
                # Insert a new row and receive the created model object.
                EmailAddress.objects.create(user=user, email=email, primary=True, verified=False)
                # Insert a new row and receive the created model object.
                UserPreferences.objects.create(user=user, display_name=data["display_name"].strip())
                # Call issue_token with the inputs shown; its definition explains the checks, side
                # effects and return value.
                issue_token(user, "verify")
        # Handle IntegrityError here. The original exception is not automatically safe to expose
        # to the client.
        except IntegrityError:
            # Intentionally do nothing in this branch; the surrounding function continues
            # afterward.
            pass  # A concurrent registration must not disclose account existence.
    # Return the result to the caller: call Response with the inputs shown; its definition
    # explains the checks, side effects and return value.
    return Response(MESSAGE, status=202)


# Check email/password and verification, then let Django create/rotate the browser session.
def login(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # user holds the Django account involved in this action; do not confuse it with the client-
    # submitted email string. Next, evaluate this lookup and return one row, or None when no row
    # matches.
    user = User.objects.filter(email__iexact=data["email"].strip()).first()
    # Always run a password hash, including nonexistent accounts.
    # candidate holds a possible existing snapshot ID, or a real/dummy user used during password
    # checking. Next, evaluate user or User(password='').
    candidate = user or User(password="")
    # valid holds whether the submitted password passed the account password-hash comparison.
    # Next, call candidate.check_password with the inputs shown; its definition explains the
    # checks, side effects and return value.
    valid = candidate.check_password(data["password"])
    # Enter this branch only when not user or not valid or (not user.is_active). Otherwise
    # execution uses its alternative or continues below.
    if not user or not valid or not user.is_active:
        # Enter this branch only when not user. Otherwise execution uses its alternative or
        # continues below.
        if not user:
            # Call user().set_password with the inputs shown; its definition explains the checks,
            # side effects and return value.
            User().set_password(data["password"])
        # Stop this action with safe API error 'authentication_required' (HTTP 401). The common
        # handler builds its JSON envelope.
        raise APIError("authentication_required", "Invalid email or password.", 401)
    # Enter this branch only when not EmailAddress.objects.filter(user=user,
    # verified=True).exists(). Otherwise execution uses its alternative or continues below.
    if not EmailAddress.objects.filter(user=user, verified=True).exists():
        # Stop this action with safe API error 'email_unverified' (HTTP 403). The common handler
        # builds its JSON envelope.
        raise APIError("email_unverified", "Verify your email before logging in.", 403)
    # Call session_login with the inputs shown; its definition explains the checks, side effects
    # and return value.
    session_login(request._request, user, backend="django.contrib.auth.backends.ModelBackend")
    # Return this named-field dictionary; API handlers turn it into JSON, while helper callers use
    # it directly.
    return {"user": user_data(user), "csrf_token": get_token(request._request)}


# End the current session and return an intentionally empty HTTP 204 response.
def logout(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # Call session_logout with the inputs shown; its definition explains the checks, side effects
    # and return value.
    session_logout(request._request)
    # Return the result to the caller: call Response with the inputs shown; its definition
    # explains the checks, side effects and return value.
    return Response(status=204)


# Ask Django for a masked CSRF token; middleware also sends the matching cookie to the browser.
def csrf(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # Return this named-field dictionary; API handlers turn it into JSON, while helper callers use
    # it directly.
    return {"csrf_token": get_token(request._request)}


# Handle verification/resend or password-reset requests without confirming that an account
# exists.
def send_instructions(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # Call email_ready with the inputs shown; its definition explains the checks, side effects and
    # return value.
    email_ready()
    # user holds the Django account involved in this action; do not confuse it with the client-
    # submitted email string. Next, evaluate this lookup and return one row, or None when no row
    # matches.
    user = User.objects.filter(email__iexact=data["email"].strip(), is_active=True).first()
    # purpose holds whether this one-time token verifies an email or resets a password. Next,
    # choose 'reset' when '/password/' in request.path; otherwise use 'verify'.
    purpose = "reset" if "/password/" in request.path else "verify"
    # Enter this branch only when user and (purpose == 'reset' and user.has_usable_password() or
    # (purpose == 'verify' and (not EmailAddress.objects.filter(user=user,
    # verified=True).exists()))). Otherwise execution uses its alternative or continues below.
    if user and (
        purpose == "reset"
        and user.has_usable_password()
        or purpose == "verify"
        and not EmailAddress.objects.filter(user=user, verified=True).exists()
    ):
        # Call issue_token with the inputs shown; its definition explains the checks, side effects
        # and return value.
        issue_token(user, purpose)
    # Return the result to the caller: call Response with the inputs shown; its definition
    # explains the checks, side effects and return value.
    return Response(MESSAGE, status=202)


# Lock and consume one valid email token; verify the email or change the password atomically.
@transaction.atomic
def consume_token(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # purpose holds whether this one-time token verifies an email or resets a password. Next,
    # choose 'reset' when '/password/' in request.path; otherwise use 'verify'.
    purpose = "reset" if "/password/" in request.path else "verify"
    # Set token: evaluate this lookup and return one row, or None when no row matches.
    token = (
        AccountToken.objects.select_for_update()
        .filter(
            token_hash=digest(data["token"]),
            purpose=purpose,
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .first()
    )
    # Enter this branch only when not token. Otherwise execution uses its alternative or continues
    # below.
    if not token:
        # Stop this action with safe API error 'invalid_token' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError("invalid_token", "Invalid or expired token.")
    # user holds the Django account involved in this action; do not confuse it with the client-
    # submitted email string. Next, look up a named setting/value or make the indicated GET call;
    # the surrounding object determines which.
    user = User.objects.select_for_update().get(pk=token.user_id)
    # Enter this branch only when not user.is_active. Otherwise execution uses its alternative or
    # continues below.
    if not user.is_active:
        # Stop this action with safe API error 'invalid_token' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError("invalid_token", "Invalid or expired token.")
    # Enter this branch only when purpose == 'reset'. Otherwise execution uses its alternative or
    # continues below.
    if purpose == "reset":
        # Call password_check with the inputs shown; its definition explains the checks, side
        # effects and return value.
        password_check(data["password"], user)
        # Call user.set_password with the inputs shown; its definition explains the checks, side
        # effects and return value.
        user.set_password(data["password"])
        # Write this model object changes to the database; update_fields, when present, limits the
        # written columns.
        user.save(update_fields=["password"])
        # Django session auth hashes invalidate all existing sessions after password change.
    else:
        # Update a matching row or insert one; receive the row and a created/not-created flag.
        EmailAddress.objects.update_or_create(
            user=user, email=user.email, defaults={"primary": True, "verified": True}
        )
    # Set token.consumed_at: call timezone.now with the inputs shown; its definition explains the
    # checks, side effects and return value.
    token.consumed_at = timezone.now()
    # Write this model object changes to the database; update_fields, when present, limits the
    # written columns.
    token.save(update_fields=["consumed_at"])
    # Write these fields directly on the matching rows through the orm.
    AccountToken.objects.filter(user=user, purpose=purpose, consumed_at__isnull=True).update(
        consumed_at=token.consumed_at
    )
    # Return this named-field dictionary; API handlers turn it into JSON, while helper callers use
    # it directly.
    return {
        "detail": "Password updated. Log in again."
        if purpose == "reset"
        else "Email verified. You can now log in."
    }


# Read the current profile, or update only the profile/preference fields permitted by the
# contract.
def me(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # Enter this branch only when request.method == 'PATCH'. Otherwise execution uses its
    # alternative or continues below.
    if request.method == "PATCH":
        # Import validate_locale from catalog.services (our TMDB/normalization layer).
        from catalog.services import validate_locale

        # Start an atomic write boundary. Leaving normally commits it; an exception rolls back
        # this block changes.
        with transaction.atomic():
            # Look up a named setting/value or make the indicated get call; the surrounding object
            # determines which.
            User.objects.select_for_update().get(pk=request.user.pk)
            # Set (pref, _): reuse a matching row or insert one; the second returned value says
            # whether it was newly created.
            pref, _ = UserPreferences.objects.get_or_create(user=request.user)
            # Enter this branch only when 'display_name' in data. Otherwise execution uses its
            # alternative or continues below.
            if "display_name" in data:
                # name holds a display name or field label; collection names are trimmed and
                # checked for allowed length. Next, call data['display_name'].strip with the
                # inputs shown; its definition explains the checks, side effects and return value.
                name = data["display_name"].strip()
                # Enter this branch only when not name. Otherwise execution uses its alternative
                # or continues below.
                if not name:
                    # Stop this action with safe API error 'validation_error' (HTTP 400). The
                    # common handler builds its JSON envelope.
                    raise APIError("validation_error", "Display name cannot be blank.")
                # Set pref.display_name: reuse name, which was prepared earlier in this function.
                pref.display_name = name
            # preferences holds only the nested preference fields supplied in this profile update.
            # Next, look up a named setting/value or make the indicated GET call; the surrounding
            # object determines which.
            preferences = data.get("preferences", {})
            # Call validate_locale with the inputs shown; its definition explains the checks, side
            # effects and return value.
            validate_locale(
                preferences.get("language", pref.display_language),
                preferences.get("region", pref.region),
            )
            # Set pref.display_language: look up a named setting/value or make the indicated GET
            # call; the surrounding object determines which.
            pref.display_language = preferences.get("language", pref.display_language)
            # Set pref.region: look up a named setting/value or make the indicated GET call; the
            # surrounding object determines which.
            pref.region = preferences.get("region", pref.region)
            # Write this model object changes to the database; update_fields, when present, limits
            # the written columns.
            pref.save()
    # Return the result to the caller: call user_data with the inputs shown; its definition
    # explains the checks, side effects and return value.
    return user_data(request.user)
