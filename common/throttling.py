"""Shared, transactionally serialized request counters for serverless instances."""

from datetime import timedelta
from ipaddress import ip_address

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from catalog.models import RateLimitBucket
from common.errors import APIError


def client_ip(request):
    # Trust only the platform-supplied IP on Vercel. Generic forwarded headers from
    # arbitrary clients are not an identity boundary on a local/self-hosted server.
    address = request.META.get("REMOTE_ADDR", "unknown")
    if settings.IS_VERCEL:
        address = request.META.get("HTTP_X_VERCEL_FORWARDED_FOR", address)
    try:
        return str(ip_address(address))
    except ValueError:
        return "unknown"


def consume(scope, identity, limit):
    if not settings.API_THROTTLING_ENABLED:
        return
    now = timezone.now()
    window = int(now.timestamp()) // 60
    # A keyed digest prevents offline guessing of email addresses from bucket keys.
    key = salted_hmac(
        "cinescope.throttle", f"{scope}:{window}:{identity}", algorithm="sha256"
    ).hexdigest()
    with transaction.atomic():
        # get_or_create handles a concurrent first insert via the unique primary key.
        # Existing rows stay locked until the increment is committed. Cache eviction
        # cannot reset this counter, and PostgreSQL workers cannot lose increments.
        bucket, _ = RateLimitBucket.objects.select_for_update().get_or_create(
            key=key, defaults={"expires_at": now + timedelta(seconds=120)}
        )
        allowed = bucket.count < limit
        if allowed:
            bucket.count += 1
            bucket.save(update_fields=["count"])
    # Raise after committing: denied requests must not roll back the limit state.
    if not allowed:
        raise APIError(
            "rate_limited", "Too many requests.", 429, retry_after=60 - int(now.timestamp()) % 60
        )


def request_limit(request):
    authenticated = request.user.is_authenticated
    identity = f"user:{request.user.pk}" if authenticated else f"ip:{client_ip(request)}"
    scope, limit = ("read", 60) if request.method in ("GET", "HEAD") else ("write", 60)
    if "/auth/" in request.path and request.method not in ("GET", "HEAD"):
        # Password/token/OAuth operations share an allowance; CSRF bootstrap is a read.
        scope, limit = "auth", 5
        identity = f"ip:{client_ip(request)}"
    elif "guest-sync" in request.path:
        scope, limit = "sync", 5
    elif "recommendations" in request.path:
        scope, limit = "recommend", 30 if authenticated else 10
    elif "/shared/" in request.path:
        scope, limit = "share", 30
    consume(scope, identity, limit)


def email_limit(request, data):
    # The IP allowance alone cannot stop distributed password guessing/email spam.
    if "/auth/" in request.path and data.get("email"):
        consume("auth", "email:" + data["email"].strip().casefold(), 5)
