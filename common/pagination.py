import hashlib
import json
import uuid
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from common.errors import APIError


def snapshot_page(request, params, factory, scope, coverage="complete", candidate_limit=None):
    page = params.get("page", 1)
    size = params.get("page_size", 20)
    token = params.get("snapshot")
    params = {**params, "page_size": size}
    signature = hashlib.sha256(
        json.dumps(
            {k: v for k, v in params.items() if k not in ("page", "snapshot")}, sort_keys=True
        ).encode()
    ).hexdigest()
    binding = f"{request.path}:{scope}"
    index_key = (
        "snapshot-index:" + hashlib.sha256(f"{binding}:{signature}:{size}".encode()).hexdigest()
    )
    # Catalogue snapshots are safe to reuse; private/share lists must start fresh
    # after writes and therefore don't use this public query index.
    if not token and page == 1 and scope == "public":
        candidate = cache.get(index_key)
        if candidate and cache.get(f"snapshot:{candidate}"):
            token = candidate
    if token:
        entry = cache.get(f"snapshot:{token}")
        if not entry:
            raise APIError("snapshot_expired", "Result snapshot expired. Restart at page 1.", 410)
        if entry["binding"] != binding or entry["signature"] != signature or entry["size"] != size:
            raise APIError("snapshot_mismatch", "Snapshot does not match this query.")
    else:
        if page != 1:
            raise APIError("validation_error", "snapshot is required after page 1.")
        token = str(uuid.uuid4())
        entry = {
            "binding": binding,
            "signature": signature,
            "size": size,
            "results": factory(),
            "expires_at": (timezone.now() + timedelta(seconds=300)).isoformat(),
            "coverage": coverage,
            "candidate_limit": candidate_limit,
        }
        cache.set(f"snapshot:{token}", entry, 300)
        if scope == "public":
            cache.set(index_key, token, 300)
    count = len(entry["results"])
    if page > max(1, (count + size - 1) // size):
        raise APIError("not_found", "Page not found.", 404)

    def link(number):
        query = dict(request.query_params.items())
        query.update(page=number, page_size=size, snapshot=token)
        base = settings.BACKEND_PUBLIC_ORIGIN or request.build_absolute_uri("/").rstrip("/")
        return f"{base}{request.path}?{urlencode(query)}"

    return {
        "count": count,
        "next": link(page + 1) if page * size < count else None,
        "previous": link(page - 1) if page > 1 else None,
        "results": entry["results"][(page - 1) * size : page * size],
        "meta": {
            "snapshot": token,
            "expires_at": entry["expires_at"],
            "coverage": entry["coverage"],
            "candidate_limit": entry["candidate_limit"],
            "warnings": [],
        },
    }
