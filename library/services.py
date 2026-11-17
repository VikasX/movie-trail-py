import hashlib
import re
import secrets
import uuid
from collections import defaultdict
from datetime import timedelta
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.response import Response

from catalog.models import TitleSnapshot
from catalog.normalization import summary
from catalog.services import raw_detail
from common.errors import APIError
from common.pagination import snapshot_page
from library.models import (
    Collection,
    CollectionMembership,
    GuestCollectionMapping,
    PublicShare,
    RecentTitle,
    SavedTitle,
)


def lock_user(user):
    get_user_model().objects.select_for_update().get(pk=user.pk)


def identity(params):
    return params["media_type"], params["tmdb_id"]


def resolve_title(media, tmdb_id):
    existing = TitleSnapshot.objects.filter(media_type=media, tmdb_id=tmdb_id).first()
    if existing:
        return existing.summary
    return summary(raw_detail(media, tmdb_id), media)


def persist_title(data):
    row, _ = TitleSnapshot.objects.get_or_create(
        media_type=data["media_type"],
        tmdb_id=data["tmdb_id"],
        defaults={"summary": data, "genre_keys": [g["key"] for g in data["genres"]]},
    )
    return row


def stored_summary(title):
    result = dict(title.summary)
    if timezone.now() - title.fetched_at > timedelta(hours=6):
        result["metadata_status"] = "stale"
    return result


def saved_data(row):
    return {
        "title": stored_summary(row.title),
        "watched": row.watched,
        "saved_at": row.saved_at.isoformat(),
        "watched_at": row.watched_at.isoformat() if row.watched_at else None,
    }


def saved_rows(user):
    return list(
        SavedTitle.objects.filter(user=user)
        .select_related("title")
        .order_by("-saved_at", "title__media_type", "title__tmdb_id")
    )


def ensure_saved(user, title):
    existing = SavedTitle.objects.filter(user=user, title=title).first()
    if existing:
        return existing
    if SavedTitle.objects.filter(user=user).count() >= 5000:
        raise APIError("account_limit", "Saved title limit reached.", 409)
    return SavedTitle.objects.create(user=user, title=title)


def library(request, params, data):
    def fetch():
        rows = saved_rows(request.user)
        if "watched" in params:
            rows = [r for r in rows if r.watched == params["watched"]]
        if "media_type" in params:
            rows = [r for r in rows if r.title.media_type == params["media_type"]]
        if params.get("sort") == "title_asc":
            rows.sort(
                key=lambda r: (
                    r.title.summary["title"].casefold(),
                    r.title.media_type,
                    r.title.tmdb_id,
                )
            )
        return [saved_data(r) for r in rows]

    return snapshot_page(request, params, fetch, f"user:{request.user.pk}")


def saved_title(request, params, data):
    media, tmdb_id = identity(params)
    resolved = None if request.method == "DELETE" else resolve_title(media, tmdb_id)
    with transaction.atomic():
        lock_user(request.user)
        if request.method == "DELETE":
            affected = Collection.objects.filter(
                user=request.user,
                memberships__saved_title__title__media_type=media,
                memberships__saved_title__title__tmdb_id=tmdb_id,
            )
            affected.update(updated_at=timezone.now())
            SavedTitle.objects.filter(
                user=request.user, title__media_type=media, title__tmdb_id=tmdb_id
            ).delete()
            return Response(status=204)
        title = persist_title(resolved)
        row = ensure_saved(request.user, title)
        watched = data["watched"]
        if watched and not row.watched:
            row.watched_at = timezone.now()
        elif not watched:
            row.watched_at = None
        row.watched = watched
        row.save()
        return saved_data(row)


def collection_name(name):
    name = name.strip()
    if not name or len(name) > 80:
        raise APIError("validation_error", "Collection name must contain 1–80 characters.")
    return name


def owned_collection(user, collection_id, mutable=False):
    if collection_id.startswith("auto:"):
        if mutable:
            raise APIError("immutable_collection", "Automatic collections are read-only.", 403)
        return None
    try:
        uuid.UUID(collection_id)
    except ValueError:
        raise APIError("not_found", "Collection not found.", 404) from None
    row = Collection.objects.filter(pk=collection_id, user=user).select_related("share").first()
    if not row:
        raise APIError("not_found", "Collection not found.", 404)
    return row


def cipher():
    try:
        return Fernet(settings.SHARE_TOKEN_ENCRYPTION_KEY.encode())
    except (ValueError, TypeError):
        raise APIError("service_unavailable", "Share encryption is not configured.", 503) from None


def share_url(token):
    origin = settings.FRONTEND_PUBLIC_ORIGIN
    parsed = urlsplit(origin)
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.scheme not in (("http", "https") if settings.DEBUG else ("https",))
    ):
        raise APIError("service_unavailable", "Public frontend origin is not configured.", 503)
    return origin.rstrip("/") + "/shared/" + token


def active_share(row):
    try:
        share = row.share
    except PublicShare.DoesNotExist:
        return None
    if not share.enabled:
        return None
    try:
        token = cipher().decrypt(share.encrypted_token.encode()).decode()
    except InvalidToken:
        raise APIError(
            "service_unavailable", "Share key requires operator attention.", 503
        ) from None
    return share_url(token)


def collection_data(row, count=None):
    url = active_share(row)
    return {
        "id": str(row.pk),
        "kind": "custom",
        "name": row.name,
        "item_count": count if count is not None else row.memberships.count(),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "sharing_enabled": bool(url),
        "share_url": url,
    }


def automatic(user):
    groups = defaultdict(list)
    for row in saved_rows(user):
        title = row.title.summary
        for genre in row.title.genre_keys:
            groups[f"auto:genre:{genre}"].append(row)
        year = title.get("year")
        if year:
            groups[f"auto:decade:{year // 10 * 10}"].append(row)
        if title.get("rating") is not None and title["rating"] >= 8:
            groups["auto:highly-rated"].append(row)
        groups["auto:movies" if row.title.media_type == "movie" else "auto:tv"].append(row)
        if row.watched:
            groups["auto:watched"].append(row)
    return groups


def auto_data(key, rows):
    name = {
        "auto:movies": "Movies",
        "auto:tv": "TV Series",
        "auto:highly-rated": "Highly Rated",
        "auto:watched": "Watched",
    }.get(key)
    if key.startswith("auto:genre:"):
        name = key.split(":")[-1].replace("-", " ").title()
    elif key.startswith("auto:decade:"):
        name = key.split(":")[-1] + "s"
    return {
        "id": key,
        "kind": "automatic",
        "name": name or key,
        "item_count": len(rows),
        "created_at": None,
        "updated_at": None,
        "sharing_enabled": False,
        "share_url": None,
    }


def collections(request, params, data):
    if request.method == "POST":
        name = collection_name(data["name"])
        with transaction.atomic():
            lock_user(request.user)
            if Collection.objects.filter(user=request.user).count() >= 100:
                raise APIError("account_limit", "Collection limit reached.", 409)
            row = Collection.objects.create(user=request.user, name=name)
        return Response(collection_data(row), status=201)

    def fetch():
        rows = (
            Collection.objects.filter(user=request.user)
            .select_related("share")
            .annotate(total=Count("memberships"))
            .order_by("-updated_at", "id")
        )
        result = [collection_data(row, row.total) for row in rows]
        result += [
            auto_data(key, values) for key, values in sorted(automatic(request.user).items())
        ]
        return result

    return snapshot_page(request, params, fetch, f"user:{request.user.pk}")


def collection_detail(request, params, data):
    key = params["collection_id"]
    if request.method != "GET":
        with transaction.atomic():
            lock_user(request.user)
            row = owned_collection(request.user, key, mutable=True)
            if request.method == "DELETE":
                GuestCollectionMapping.objects.filter(collection=row).update(
                    deleted_at=timezone.now()
                )
                row.delete()
                return Response(status=204)
            row.name = collection_name(data["name"])
            row.save()
            return collection_data(row)
    row = owned_collection(request.user, key)
    if row is None:
        groups = automatic(request.user)
        if key not in groups:
            raise APIError("not_found", "Collection not found.", 404)
        rows = groups[key]
        value = auto_data(key, rows)

        def items():
            return [{"title": stored_summary(r.title), "added_at": None} for r in rows]
    else:
        value = collection_data(row)

        def items():
            return membership_data(row)

    page = snapshot_page(request, params, items, f"user:{request.user.pk}:collection:{key}")
    return {"collection": value, "items": page}


def membership_data(collection):
    return [
        {"title": stored_summary(r.saved_title.title), "added_at": r.added_at.isoformat()}
        for r in collection.memberships.select_related("saved_title__title").order_by(
            "-added_at", "saved_title__title__media_type", "saved_title__title__tmdb_id"
        )
    ]


def membership(request, params, data):
    # Ownership before external lookup prevents another user's UUID acting as a probe.
    owned_collection(request.user, params["collection_id"], mutable=True)
    resolved = resolve_title(*identity(params)) if request.method == "PUT" else None
    with transaction.atomic():
        lock_user(request.user)
        row = owned_collection(request.user, params["collection_id"], mutable=True)
        if request.method == "DELETE":
            row.memberships.filter(
                saved_title__title__media_type=params["media_type"],
                saved_title__title__tmdb_id=params["tmdb_id"],
            ).delete()
            row.save(update_fields=["updated_at"])
            return Response(status=204)
        title = persist_title(resolved)
        saved = ensure_saved(request.user, title)
        existing = row.memberships.filter(saved_title=saved).first()
        if not existing and row.memberships.count() >= 500:
            raise APIError("collection_limit", "Collection item limit reached.", 409)
        member = existing or CollectionMembership.objects.create(collection=row, saved_title=saved)
        row.save(update_fields=["updated_at"])
        return {"title": stored_summary(title), "added_at": member.added_at.isoformat()}


def sharing(request, params, data):
    with transaction.atomic():
        lock_user(request.user)
        row = owned_collection(request.user, params["collection_id"], mutable=True)
        if request.method == "DELETE":
            PublicShare.objects.filter(collection=row).update(
                enabled=False, revoked_at=timezone.now()
            )
            return Response(status=204)
        existing = active_share(row)
        if existing:
            return {"enabled": True, "url": existing}
        token = secrets.token_urlsafe(32)
        url = share_url(token)
        PublicShare.objects.update_or_create(
            collection=row,
            defaults={
                "enabled": True,
                "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                "encrypted_token": cipher().encrypt(token.encode()).decode(),
                "revoked_at": None,
            },
        )
        return {"enabled": True, "url": url}


def shared(request, params, data):
    token = params["token"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", token):
        raise APIError("not_found", "Collection not found.", 404)
    row = (
        PublicShare.objects.filter(
            token_hash=hashlib.sha256(token.encode()).hexdigest(), enabled=True
        )
        .select_related("collection")
        .first()
    )
    if not row:
        raise APIError("not_found", "Collection not found.", 404)
    # Capability is verified on EVERY page, before accessing any cached snapshot.
    page = snapshot_page(
        request, params, lambda: membership_data(row.collection), f"share:{row.pk}:{row.token_hash}"
    )
    return {"name": row.collection.name, "items": page}


def recent(request, params, data):
    def fetch():
        return [
            {"title": stored_summary(r.title), "explored_at": r.explored_at.isoformat()}
            for r in RecentTitle.objects.filter(user=request.user)
            .select_related("title")
            .order_by("-explored_at", "title__media_type", "title__tmdb_id")[:50]
        ]

    return snapshot_page(request, params, fetch, f"user:{request.user.pk}")


def record_recent(request, params, data):
    title_data = resolve_title(*identity(params))
    with transaction.atomic():
        lock_user(request.user)
        title = persist_title(title_data)
        row, _ = RecentTitle.objects.update_or_create(
            user=request.user, title=title, defaults={"explored_at": timezone.now()}
        )
        keep = list(
            RecentTitle.objects.filter(user=request.user)
            .order_by("-explored_at", "pk")
            .values_list("pk", flat=True)[:50]
        )
        RecentTitle.objects.filter(user=request.user).exclude(pk__in=keep).delete()
        return {"title": stored_summary(title), "explored_at": row.explored_at.isoformat()}
