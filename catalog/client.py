# FILE PURPOSE: The shared HTTP doorway to TMDB: credentials, cache, time budget and safe
# failures.
# Import hashlib so the code below can use that module namespace.
import hashlib

# Import json so the code below can use that module namespace.
import json

# Import time so the code below can use that module namespace.
import time

# Import ContextVar from contextvars (the named Python helper module).
from contextvars import ContextVar

# Import httpx so the code below can use that module namespace.
import httpx

# Import settings from django.conf (Django framework/database/security helpers).
from django.conf import settings

# Import cache from django.core.cache (Django framework/database/security helpers).
from django.core.cache import cache

# Import APIError from common.errors (our shared API layer).
from common.errors import APIError

# Set _budget: call ContextVar with the inputs shown; its definition explains the checks, side
# effects and return value.
_budget = ContextVar("tmdb_budget", default=None)


# Start this request with zero TMDB attempts and a deadline fifteen seconds from now.
def start_budget():
    # Make a set so duplicate entries disappear and membership checks are straightforward.
    _budget.set({"attempts": 0, "deadline": time.monotonic() + 15})


# Responsible for external HTTP communication only; feature services decide what data to
# request.
class TMDBClient:
    # Read/cache/retry one external TMDB request while keeping credentials out of the response
    # and logs.
    def get(self, path, params=None, ttl=300, missing_ok=False):
        # INPUTS TO THIS FUNCTION: self = this class instance; path = argument supplied by the
        # caller; params = cleaned URL/query values; ttl = argument supplied by the caller;
        # missing_ok = argument supplied by the caller.
        # budget holds this request shared counter and external-call deadline; all its TMDB
        # helpers consume the same allowance. Next, look up a named setting/value or make the
        # indicated GET call; the surrounding object determines which.
        budget = _budget.get()
        # Enter this branch only when budget is None. Otherwise execution uses its alternative or
        # continues below.
        if budget is None:
            # Call start_budget with the inputs shown; its definition explains the checks, side
            # effects and return value.
            start_budget()
            # budget holds this request shared counter and external-call deadline; all its TMDB
            # helpers consume the same allowance. Next, look up a named setting/value or make the
            # indicated GET call; the surrounding object determines which.
            budget = _budget.get()
        # params holds path/query settings; this name can also mean outbound TMDB parameters
        # inside catalogue helpers. Next, build a lookup dictionary for each (k, v) in (params or
        # {}).items(); keep only entries passing v is not None.
        params = {k: v for k, v in (params or {}).items() if v is not None}
        # Make an order-stable cache identity from the endpoint and its parameters, excluding
        # credentials.
        # fingerprint holds a deterministic hash/input identity; sorting keys makes equivalent
        # dictionaries compare consistently. Next, call json.dumps with the inputs shown; its
        # definition explains the checks, side effects and return value.
        fingerprint = json.dumps([path, params], sort_keys=True)
        # Set key: calculate 'tmdb:v2:' + hashlib.sha256(fingerprint.encode()).hexdigest() from
        # the intermediate values already prepared.
        key = "tmdb:v2:" + hashlib.sha256(fingerprint.encode()).hexdigest()
        # A cached result skips external HTTP; an expired/missing entry continues below.
        # hit holds a remembered shared-cache result; None means the lookup did not find a usable
        # entry. Next, read a shared cache entry, or None on a miss.
        hit = cache.get(key)
        # A cache entry exists, including deliberately cached negative results; distinguish this
        # from a cache miss.
        if hit is not None:
            # Enter this branch only when hit == {'_not_found': True}. Otherwise execution uses
            # its alternative or continues below.
            if hit == {"_not_found": True}:
                # Stop this action with safe API error 'not_found' (HTTP 404). The common handler
                # builds its JSON envelope.
                raise APIError("not_found", "Title not found.", 404)
            # Return the result to the caller: reuse hit, which was prepared earlier in this
            # function.
            return hit
        # A recent upstream rate limit temporarily stops new fetches across Vercel instances.
        # Enter this branch only when cache.get('tmdb:backoff'). Otherwise execution uses its
        # alternative or continues below.
        if cache.get("tmdb:backoff"):
            # Stop this action with safe API error 'service_unavailable' (HTTP 503). The common
            # handler builds its JSON envelope.
            raise APIError(
                "service_unavailable", "Metadata provider is rate limited.", 503, retry_after=30
            )
        # Set token: read settings.TMDB_READ_ACCESS_TOKEN from the indicated object.
        token = settings.TMDB_READ_ACCESS_TOKEN
        # Enter this branch only when not token and (not settings.TMDB_API_KEY). Otherwise
        # execution uses its alternative or continues below.
        if not token and not settings.TMDB_API_KEY:
            # Stop this action with safe API error 'service_unavailable' (HTTP 503). The common
            # handler builds its JSON envelope.
            raise APIError("service_unavailable", "Metadata provider is not configured.", 503)
        # headers holds HTTP headers sent to the external service; backend credentials belong
        # here, never in React data. Next, build a dictionary with named fields such as Accept.
        headers = {"Accept": "application/json"}
        # The caller supplied a continuation/capability token; its validity still needs checking.
        if token:
            # Set headers['Authorization']: evaluate f'Bearer {token}'.
            headers["Authorization"] = f"Bearer {token}"
        else:
            # Set params['api_key']: read settings.TMDB_API_KEY from the indicated object.
            params["api_key"] = settings.TMDB_API_KEY
        # Short shared lease coalesces cache misses across serverless instances.
        # Import lease from catalog.leases (our TMDB/normalization layer).
        from catalog.leases import lease

        # Only one refresher should fetch this key; recheck cache after acquiring the shared
        # lease.
        # Hold the short shared refresh lease while this work runs, then release it in the helper
        # finally block.
        with lease(key):
            # hit holds a remembered shared-cache result; None means the lookup did not find a
            # usable entry. Next, read a shared cache entry, or None on a miss.
            hit = cache.get(key)
            # A cache entry exists, including deliberately cached negative results; distinguish
            # this from a cache miss.
            if hit is not None:
                # Enter this branch only when hit == {'_not_found': True}. Otherwise execution
                # uses its alternative or continues below.
                if hit == {"_not_found": True}:
                    # Stop this action with safe API error 'not_found' (HTTP 404). The common
                    # handler builds its JSON envelope.
                    raise APIError("not_found", "Title not found.", 404)
                # Return the result to the caller: reuse hit, which was prepared earlier in this
                # function.
                return hit
            # At most an initial attempt and one retry, still subject to the whole-request
            # budget.
            # Repeat the following block for each attempt from range(2). Each iteration handles
            # that one item/pair.
            for attempt in range(2):
                # remaining holds seconds left before the external-work deadline, measured by a
                # monotonic clock. Next, subtract the right-hand value or set from the left-hand
                # one.
                remaining = budget["deadline"] - time.monotonic()
                # Enter this branch only when remaining <= 0 or budget['attempts'] >= 8. Otherwise
                # execution uses its alternative or continues below.
                if remaining <= 0 or budget["attempts"] >= 8:
                    # Stop this action with safe API error 'upstream_timeout' (HTTP 504). The
                    # common handler builds its JSON envelope.
                    raise APIError("upstream_timeout", "Metadata request budget exhausted.", 504)
                # Add to budget['attempts'] using use the fixed value 1.
                budget["attempts"] += 1
                # Attempt this block; the following except branches handle expected failures
                # without continuing the success path.
                try:
                    # Open an HTTP client for this block; leaving it closes its network resources
                    # even when a request fails.
                    with httpx.Client(
                        timeout=httpx.Timeout(min(5, remaining), connect=min(2, remaining)),
                        follow_redirects=False,
                    ) as client:
                        # response holds the response produced by the next handler or external
                        # HTTP request. Next, look up a named setting/value or make the indicated
                        # GET call; the surrounding object determines which.
                        response = client.get(
                            settings.TMDB_BASE_URL + "/" + path.lstrip("/"),
                            params=params,
                            headers=headers,
                        )
                # Handle httpx.TimeoutException here. The original exception is not automatically
                # safe to expose to the client.
                except httpx.TimeoutException:
                    # Enter this branch only when attempt == 0 and budget['attempts'] < 8 and
                    # (time.monotonic() + 1 < budget['deadline']). Otherwise execution uses its
                    # alternative or continues below.
                    if (
                        attempt == 0
                        and budget["attempts"] < 8
                        and time.monotonic() + 1 < budget["deadline"]
                    ):
                        # Skip the rest of this iteration and move to the next item or allowed
                        # retry.
                        continue
                    # Stop this action with safe API error 'upstream_timeout' (HTTP 504). The
                    # common handler builds its JSON envelope.
                    raise APIError(
                        "upstream_timeout", "Metadata provider timed out.", 504
                    ) from None
                # Handle httpx.HTTPError here. The original exception is not automatically safe to
                # expose to the client.
                except httpx.HTTPError:
                    # Enter this branch only when attempt == 0 and budget['attempts'] < 8 and
                    # (time.monotonic() + 1 < budget['deadline']). Otherwise execution uses its
                    # alternative or continues below.
                    if (
                        attempt == 0
                        and budget["attempts"] < 8
                        and time.monotonic() + 1 < budget["deadline"]
                    ):
                        # Call time.sleep with the inputs shown; its definition explains the
                        # checks, side effects and return value.
                        time.sleep(0.05)
                        # Skip the rest of this iteration and move to the next item or allowed
                        # retry.
                        continue
                    # Stop this action with safe API error 'service_unavailable' (HTTP 503). The
                    # common handler builds its JSON envelope.
                    raise APIError(
                        "service_unavailable", "Metadata provider is unavailable.", 503
                    ) from None
                # TMDB throttling is a temporary dependency failure; remember its retry delay,
                # not its raw body.
                # Enter this branch only when response.status_code == 429. Otherwise execution
                # uses its alternative or continues below.
                if response.status_code == 429:
                    # Attempt this block; the following except branches handle expected failures
                    # without continuing the success path.
                    try:
                        # Set delay: choose the largest value, or apply the shown fallback/bound.
                        delay = max(1, min(300, int(response.headers.get("Retry-After", "30"))))
                    # Handle ValueError here. The original exception is not automatically safe to
                    # expose to the client.
                    except ValueError:
                        # Set delay: use the fixed value 30.
                        delay = 30
                    # Remember this value for the specified lifetime.
                    cache.set("tmdb:backoff", True, delay)
                    # Stop this action with safe API error 'service_unavailable' (HTTP 503). The
                    # common handler builds its JSON envelope.
                    raise APIError(
                        "service_unavailable",
                        "Metadata provider is rate limited.",
                        503,
                        retry_after=delay,
                    )
                # Enter this branch only when response.status_code == 404. Otherwise execution
                # uses its alternative or continues below.
                if response.status_code == 404:
                    # Enter this branch only when missing_ok. Otherwise execution uses its
                    # alternative or continues below.
                    if missing_ok:
                        # Remember this value for the specified lifetime.
                        cache.set(key, {"_not_found": True}, 60)
                    # Stop this action with safe API error 'not_found' (HTTP 404). The common
                    # handler builds its JSON envelope.
                    raise APIError("not_found", "Title not found.", 404)
                # Enter this branch only when response.status_code >= 500. Otherwise execution
                # uses its alternative or continues below.
                if response.status_code >= 500:
                    # Enter this branch only when attempt == 0 and budget['attempts'] < 8 and
                    # (time.monotonic() + 1 < budget['deadline']). Otherwise execution uses its
                    # alternative or continues below.
                    if (
                        attempt == 0
                        and budget["attempts"] < 8
                        and time.monotonic() + 1 < budget["deadline"]
                    ):
                        # Call time.sleep with the inputs shown; its definition explains the
                        # checks, side effects and return value.
                        time.sleep(0.05)
                        # Skip the rest of this iteration and move to the next item or allowed
                        # retry.
                        continue
                    # Stop this action with safe API error 'service_unavailable' (HTTP 503). The
                    # common handler builds its JSON envelope.
                    raise APIError("service_unavailable", "Metadata provider is unavailable.", 503)
                # Enter this branch only when response.status_code != 200. Otherwise execution
                # uses its alternative or continues below.
                if response.status_code != 200:
                    # Stop this action with safe API error 'upstream_invalid' (HTTP 502). The
                    # common handler builds its JSON envelope.
                    raise APIError(
                        "upstream_invalid", "Metadata provider rejected the request.", 502
                    )
                # Attempt this block; the following except branches handle expected failures
                # without continuing the success path.
                try:
                    # Set result: decode the HTTP response JSON into ordinary Python
                    # dictionaries/lists.
                    result = response.json()
                # Handle ValueError here. The original exception is not automatically safe to
                # expose to the client.
                except ValueError:
                    # Stop this action with safe API error 'upstream_invalid' (HTTP 502). The
                    # common handler builds its JSON envelope.
                    raise APIError("upstream_invalid", "Invalid metadata response.", 502) from None
                # Enter this branch only when not isinstance(result, (dict, list)). Otherwise
                # execution uses its alternative or continues below.
                if not isinstance(result, (dict, list)):
                    # Stop this action with safe API error 'upstream_invalid' (HTTP 502). The
                    # common handler builds its JSON envelope.
                    raise APIError("upstream_invalid", "Invalid metadata response.", 502)
                # Enter this branch only when time.monotonic() > budget['deadline']. Otherwise
                # execution uses its alternative or continues below.
                if time.monotonic() > budget["deadline"]:
                    # Stop this action with safe API error 'upstream_timeout' (HTTP 504). The
                    # common handler builds its JSON envelope.
                    raise APIError("upstream_timeout", "Metadata request deadline exceeded.", 504)
                # Only a successful JSON response is cached here; return the same decoded data
                # to the service.
                # Remember this value for the specified lifetime.
                cache.set(key, result, ttl)
                # Return the result to the caller: reuse result, which was prepared earlier in
                # this function.
                return result
