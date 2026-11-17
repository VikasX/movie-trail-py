import hashlib
import secrets
import uuid
from datetime import timedelta
from urllib.parse import urlencode

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import login as session_login
from django.contrib.auth import logout as session_logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework.response import Response

from accounts.models import AccountToken, UserPreferences
from common.errors import APIError

User = get_user_model()
MESSAGE = {"detail": "If eligible, instructions have been sent."}


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def user_data(user):
    pref = UserPreferences.objects.filter(user=user).first() or UserPreferences(user=user)
    providers = list(user.socialaccount_set.values_list("provider", flat=True))
    if user.has_usable_password():
        providers.append("email")
    return {
        "id": user.pk,
        "email": user.email,
        "display_name": pref.display_name,
        "email_verified": EmailAddress.objects.filter(user=user, verified=True).exists(),
        "providers": sorted(set(providers)),
        "preferences": {"language": pref.display_language, "region": pref.region},
    }


def password_check(password, user=None):
    try:
        validate_password(password, user)
    except ValidationError:
        raise APIError(
            "validation_error",
            "Password does not meet security requirements.",
            fields={"password": ["Use a stronger password."]},
        ) from None


def email_ready():
    if not settings.FRONTEND_PUBLIC_ORIGIN:
        raise APIError("service_unavailable", "Email delivery is not configured.", 503)
    if not settings.DEBUG and (
        "console" in settings.EMAIL_BACKEND
        or "locmem" in settings.EMAIL_BACKEND
        or ("smtp" in settings.EMAIL_BACKEND and not settings.EMAIL_HOST)
    ):
        raise APIError("service_unavailable", "Email delivery is not configured.", 503)


def issue_token(user, purpose):
    token = secrets.token_urlsafe(48)
    record = AccountToken.objects.create(
        user=user,
        purpose=purpose,
        token_hash=digest(token),
        expires_at=timezone.now() + timedelta(hours=24 if purpose == "verify" else 1),
    )
    path = "/auth/verify-email" if purpose == "verify" else "/auth/reset-password"
    url = settings.FRONTEND_PUBLIC_ORIGIN + path + "?" + urlencode({"token": token})
    try:
        send_mail(
            "CineScope account instructions",
            f"Open this link to continue: {url}",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except Exception:
        record.delete()
        raise APIError(
            "service_unavailable", "Email delivery temporarily unavailable.", 503
        ) from None


def register(request, params, data):
    email_ready()
    email = data["email"].strip().casefold()
    password_check(data["password"], User(email=email))
    if not User.objects.filter(email__iexact=email).exists():
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=uuid.uuid4().hex, email=email, password=data["password"]
                )
                EmailAddress.objects.create(user=user, email=email, primary=True, verified=False)
                UserPreferences.objects.create(user=user, display_name=data["display_name"].strip())
                issue_token(user, "verify")
        except IntegrityError:
            pass  # A concurrent registration must not disclose account existence.
    return Response(MESSAGE, status=202)


def login(request, params, data):
    user = User.objects.filter(email__iexact=data["email"].strip()).first()
    # Always run a password hash, including nonexistent accounts.
    candidate = user or User(password="")
    valid = candidate.check_password(data["password"])
    if not user or not valid or not user.is_active:
        if not user:
            User().set_password(data["password"])
        raise APIError("authentication_required", "Invalid email or password.", 401)
    if not EmailAddress.objects.filter(user=user, verified=True).exists():
        raise APIError("email_unverified", "Verify your email before logging in.", 403)
    session_login(request._request, user, backend="django.contrib.auth.backends.ModelBackend")
    return {"user": user_data(user), "csrf_token": get_token(request._request)}


def logout(request, params, data):
    session_logout(request._request)
    return Response(status=204)


def csrf(request, params, data):
    return {"csrf_token": get_token(request._request)}


def send_instructions(request, params, data):
    email_ready()
    user = User.objects.filter(email__iexact=data["email"].strip(), is_active=True).first()
    purpose = "reset" if "/password/" in request.path else "verify"
    if user and (
        purpose == "reset"
        and user.has_usable_password()
        or purpose == "verify"
        and not EmailAddress.objects.filter(user=user, verified=True).exists()
    ):
        issue_token(user, purpose)
    return Response(MESSAGE, status=202)


@transaction.atomic
def consume_token(request, params, data):
    purpose = "reset" if "/password/" in request.path else "verify"
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
    if not token:
        raise APIError("invalid_token", "Invalid or expired token.")
    user = User.objects.select_for_update().get(pk=token.user_id)
    if not user.is_active:
        raise APIError("invalid_token", "Invalid or expired token.")
    if purpose == "reset":
        password_check(data["password"], user)
        user.set_password(data["password"])
        user.save(update_fields=["password"])
        # Django session auth hashes invalidate all existing sessions after password change.
    else:
        EmailAddress.objects.update_or_create(
            user=user, email=user.email, defaults={"primary": True, "verified": True}
        )
    token.consumed_at = timezone.now()
    token.save(update_fields=["consumed_at"])
    AccountToken.objects.filter(user=user, purpose=purpose, consumed_at__isnull=True).update(
        consumed_at=token.consumed_at
    )
    return {
        "detail": "Password updated. Log in again."
        if purpose == "reset"
        else "Email verified. You can now log in."
    }


def me(request, params, data):
    if request.method == "PATCH":
        from catalog.services import validate_locale

        with transaction.atomic():
            User.objects.select_for_update().get(pk=request.user.pk)
            pref, _ = UserPreferences.objects.get_or_create(user=request.user)
            if "display_name" in data:
                name = data["display_name"].strip()
                if not name:
                    raise APIError("validation_error", "Display name cannot be blank.")
                pref.display_name = name
            preferences = data.get("preferences", {})
            validate_locale(
                preferences.get("language", pref.display_language),
                preferences.get("region", pref.region),
            )
            pref.display_language = preferences.get("language", pref.display_language)
            pref.region = preferences.get("region", pref.region)
            pref.save()
    return user_data(request.user)
