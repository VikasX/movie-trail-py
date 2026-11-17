import hashlib
import json
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from catalog.models import TitleSnapshot
from common.errors import APIError
from library.models import (
    Collection,
    CollectionMembership,
    GuestCollectionMapping,
    SavedTitle,
    SyncReceipt,
)
from library.services import collection_name, lock_user, resolve_title


def key(value):
    return value["media_type"], value["tmdb_id"]


def validate_payload(data):
    saved = data["saved_titles"]
    collections = data["collections"]
    if len({key(v) for v in saved}) != len(saved) or len(
        {c["client_id"] for c in collections}
    ) != len(collections):
        raise APIError("validation_error", "Duplicate title or collection identifiers.")
    refs = {key(v) for v in saved}
    total = 0
    for collection in collections:
        collection_name(collection["name"])
        members = [key(v) for v in collection["items"]]
        if len(set(members)) != len(members):
            raise APIError("validation_error", "Duplicate collection members.")
        refs.update(members)
        total += len(members)
    if len(refs) > 500 or total > 2000:
        raise APIError("validation_error", "Guest import limits exceeded.")
    for row in saved:
        saved_at = parse_datetime(row["saved_at"])
        watched_at = parse_datetime(row["watched_at"]) if row["watched_at"] else None
        if (
            not saved_at
            or timezone.is_naive(saved_at)
            or (watched_at and timezone.is_naive(watched_at))
        ):
            raise APIError("validation_error", "Timestamps must include a timezone.")
        if bool(watched_at) != row["watched"] or (watched_at and watched_at < saved_at):
            raise APIError("validation_error", "Inconsistent watched timestamp.")
        if max(saved_at, watched_at or saved_at) > timezone.now() + timedelta(minutes=5):
            raise APIError("validation_error", "Future guest timestamps are not allowed.")
    return refs


def receipt_result(user, data, fingerprint):
    existing = SyncReceipt.objects.filter(
        user=user, sync_id=data["sync_id"], expires_at__gt=timezone.now()
    ).first()
    if existing:
        if existing.request_hash != fingerprint:
            raise APIError(
                "idempotency_conflict", "sync_id was already used with different data.", 409
            )
        return existing.result
    return None


def sync(request, params, data):
    refs = validate_payload(data)
    fingerprint = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    previous = receipt_result(request.user, data, fingerprint)
    if previous is not None:
        return previous
    # Resolve identities before opening a write transaction. No partial user data on failure.
    predicate = Q(media_type="movie", tmdb_id__in=[i for m, i in refs if m == "movie"]) | Q(
        media_type="tv", tmdb_id__in=[i for m, i in refs if m == "tv"]
    )
    resolved = {
        (row.media_type, row.tmdb_id): row.summary
        for row in TitleSnapshot.objects.filter(predicate)
    }
    rejected = []
    for media, tmdb_id in sorted(refs - set(resolved)):
        try:
            resolved[(media, tmdb_id)] = resolve_title(media, tmdb_id)
        except APIError as exc:
            if exc.status_code == 404:
                rejected.append(
                    {
                        "title": {"media_type": media, "tmdb_id": tmdb_id},
                        "code": "title_unavailable",
                    }
                )
            else:
                raise APIError(
                    "sync_retry_later",
                    "Import metadata is temporarily unavailable; retry the same sync_id.",
                    503,
                    retry_after=30,
                ) from None
    guest_saved = {key(row): row for row in data["saved_titles"]}
    with transaction.atomic():
        lock_user(request.user)
        previous = receipt_result(request.user, data, fingerprint)
        if previous is not None:
            return previous
        result = {
            "sync_id": data["sync_id"],
            "saved_created": 0,
            "saved_merged": 0,
            "collections_created": 0,
            "memberships_created": 0,
            "collection_mappings": [],
            "rejected_titles": rejected,
        }
        existing_saved = {
            (r.title.media_type, r.title.tmdb_id): r
            for r in SavedTitle.objects.filter(user=request.user).select_related("title")
        }
        if len(existing_saved) + len(set(resolved) - set(existing_saved)) > 5000:
            raise APIError("account_limit", "Saved title limit reached.", 409)
        created_saved, updated_saved = [], []
        now = timezone.now()
        TitleSnapshot.objects.bulk_create(
            [
                TitleSnapshot(
                    media_type=m,
                    tmdb_id=i,
                    summary=value,
                    genre_keys=[g["key"] for g in value["genres"]],
                )
                for (m, i), value in resolved.items()
            ],
            ignore_conflicts=True,
        )
        titles = {
            (row.media_type, row.tmdb_id): row for row in TitleSnapshot.objects.filter(predicate)
        }
        for ref in resolved:
            guest = guest_saved.get(ref)
            row = existing_saved.get(ref)
            if row:
                result["saved_merged"] += 1
                if guest and guest["watched"] and not row.watched:
                    row.watched = True
                    row.watched_at = parse_datetime(guest["watched_at"])
                    row.updated_at = now
                    updated_saved.append(row)
            else:
                title = titles[ref]
                row = SavedTitle(
                    user=request.user,
                    title=title,
                    watched=bool(guest and guest["watched"]),
                    saved_at=parse_datetime(guest["saved_at"]) if guest else now,
                    watched_at=parse_datetime(guest["watched_at"])
                    if guest and guest["watched"]
                    else None,
                )
                created_saved.append(row)
                result["saved_created"] += 1
        SavedTitle.objects.bulk_create(created_saved)
        if updated_saved:
            SavedTitle.objects.bulk_update(updated_saved, ["watched", "watched_at", "updated_at"])
        existing_saved = {
            (r.title.media_type, r.title.tmdb_id): r
            for r in SavedTitle.objects.filter(user=request.user).select_related("title")
        }
        used_names = {
            name.casefold()
            for name in Collection.objects.filter(user=request.user).values_list("name", flat=True)
        }
        for guest in data["collections"]:
            mapping = (
                GuestCollectionMapping.objects.filter(
                    user=request.user, guest_id=data["guest_id"], client_id=guest["client_id"]
                )
                .select_related("collection")
                .first()
            )
            if mapping and (mapping.collection is None or mapping.deleted_at):
                raise APIError(
                    "sync_source_deleted",
                    "An imported collection was deleted. Confirm before importing it again.",
                    409,
                )
            if not mapping:
                if len(used_names) >= 100:
                    raise APIError("account_limit", "Collection limit reached.", 409)
                base = collection_name(guest["name"])
                name, suffix = base, 2
                while name.casefold() in used_names:
                    tail = f" (Imported {suffix})"
                    name = base[: 80 - len(tail)] + tail
                    suffix += 1
                used_names.add(name.casefold())
                collection = Collection.objects.create(user=request.user, name=name)
                mapping = GuestCollectionMapping.objects.create(
                    user=request.user,
                    guest_id=data["guest_id"],
                    client_id=guest["client_id"],
                    collection=collection,
                )
                result["collections_created"] += 1
            collection = mapping.collection
            refs_for_collection = {key(r) for r in guest["items"]} & set(resolved)
            existing_ids = set(collection.memberships.values_list("saved_title_id", flat=True))
            new_ids = {existing_saved[ref].pk for ref in refs_for_collection} - existing_ids
            if len(existing_ids) + len(new_ids) > 500:
                raise APIError("collection_limit", "Collection item limit reached.", 409)
            CollectionMembership.objects.bulk_create(
                [CollectionMembership(collection=collection, saved_title_id=pk) for pk in new_ids]
            )
            result["memberships_created"] += len(new_ids)
            Collection.objects.filter(pk=collection.pk).update(updated_at=now)
            result["collection_mappings"].append(
                {"client_id": guest["client_id"], "collection_id": str(collection.pk)}
            )
        SyncReceipt.objects.update_or_create(
            user=request.user,
            sync_id=data["sync_id"],
            defaults={
                "request_hash": fingerprint,
                "result": result,
                "expires_at": now + timedelta(hours=24),
            },
        )
        return result
