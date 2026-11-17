import hashlib
import json
import time
from contextvars import ContextVar

import httpx
from django.conf import settings
from django.core.cache import cache

from common.errors import APIError

_budget = ContextVar("tmdb_budget", default=None)


def start_budget():
    _budget.set({"attempts": 0, "deadline": time.monotonic() + 15})


class TMDBClient:
    def get(self, path, params=None, ttl=300, missing_ok=False):
        budget = _budget.get()
        if budget is None:
            start_budget()
            budget = _budget.get()
        params = {k: v for k, v in (params or {}).items() if v is not None}
        fingerprint = json.dumps([path, params], sort_keys=True)
        key = "tmdb:v2:" + hashlib.sha256(fingerprint.encode()).hexdigest()
        hit = cache.get(key)
        if hit is not None:
            if hit == {"_not_found": True}:
                raise APIError("not_found", "Title not found.", 404)
            return hit
        if cache.get("tmdb:backoff"):
            raise APIError(
                "service_unavailable", "Metadata provider is rate limited.", 503, retry_after=30
            )
        token = settings.TMDB_READ_ACCESS_TOKEN
        if not token and not settings.TMDB_API_KEY:
            raise APIError("service_unavailable", "Metadata provider is not configured.", 503)
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            params["api_key"] = settings.TMDB_API_KEY
        # Short shared lease coalesces cache misses across serverless instances.
        from catalog.leases import lease

        with lease(key):
            hit = cache.get(key)
            if hit is not None:
                if hit == {"_not_found": True}:
                    raise APIError("not_found", "Title not found.", 404)
                return hit
            for attempt in range(2):
                remaining = budget["deadline"] - time.monotonic()
                if remaining <= 0 or budget["attempts"] >= 8:
                    raise APIError("upstream_timeout", "Metadata request budget exhausted.", 504)
                budget["attempts"] += 1
                try:
                    with httpx.Client(
                        timeout=httpx.Timeout(min(5, remaining), connect=min(2, remaining)),
                        follow_redirects=False,
                    ) as client:
                        response = client.get(
                            settings.TMDB_BASE_URL + "/" + path.lstrip("/"),
                            params=params,
                            headers=headers,
                        )
                except httpx.TimeoutException:
                    if (
                        attempt == 0
                        and budget["attempts"] < 8
                        and time.monotonic() + 1 < budget["deadline"]
                    ):
                        continue
                    raise APIError(
                        "upstream_timeout", "Metadata provider timed out.", 504
                    ) from None
                except httpx.HTTPError:
                    if (
                        attempt == 0
                        and budget["attempts"] < 8
                        and time.monotonic() + 1 < budget["deadline"]
                    ):
                        time.sleep(0.05)
                        continue
                    raise APIError(
                        "service_unavailable", "Metadata provider is unavailable.", 503
                    ) from None
                if response.status_code == 429:
                    try:
                        delay = max(1, min(300, int(response.headers.get("Retry-After", "30"))))
                    except ValueError:
                        delay = 30
                    cache.set("tmdb:backoff", True, delay)
                    raise APIError(
                        "service_unavailable",
                        "Metadata provider is rate limited.",
                        503,
                        retry_after=delay,
                    )
                if response.status_code == 404:
                    if missing_ok:
                        cache.set(key, {"_not_found": True}, 60)
                    raise APIError("not_found", "Title not found.", 404)
                if response.status_code >= 500:
                    if (
                        attempt == 0
                        and budget["attempts"] < 8
                        and time.monotonic() + 1 < budget["deadline"]
                    ):
                        time.sleep(0.05)
                        continue
                    raise APIError("service_unavailable", "Metadata provider is unavailable.", 503)
                if response.status_code != 200:
                    raise APIError(
                        "upstream_invalid", "Metadata provider rejected the request.", 502
                    )
                try:
                    result = response.json()
                except ValueError:
                    raise APIError("upstream_invalid", "Invalid metadata response.", 502) from None
                if not isinstance(result, (dict, list)):
                    raise APIError("upstream_invalid", "Invalid metadata response.", 502)
                if time.monotonic() > budget["deadline"]:
                    raise APIError("upstream_timeout", "Metadata request deadline exceeded.", 504)
                cache.set(key, result, ttl)
                return result
