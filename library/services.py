# FILE PURPOSE: Personal-library workflows and permissions; automatic groups are calculated
# here.
# Import hashlib so the code below can use that module namespace.
import hashlib

# Import re so the code below can use that module namespace.
import re

# Import secrets so the code below can use that module namespace.
import secrets

# Import uuid so the code below can use that module namespace.
import uuid

# Import defaultdict from collections (the named Python helper module).
from collections import defaultdict

# Import timedelta from datetime (the named Python helper module).
from datetime import timedelta

# Import urlsplit from urllib.parse (the named Python helper module).
from urllib.parse import urlsplit

# Import Fernet, InvalidToken from cryptography.fernet (authenticated encryption support).
from cryptography.fernet import Fernet, InvalidToken

# Import settings from django.conf (Django framework/database/security helpers).
from django.conf import settings

# Import get_user_model from django.contrib.auth (Django framework/database/security helpers).
from django.contrib.auth import get_user_model

# Import transaction from django.db (Django framework/database/security helpers).
from django.db import transaction

# Import Count from django.db.models (Django framework/database/security helpers).
from django.db.models import Count

# Import timezone from django.utils (Django framework/database/security helpers).
from django.utils import timezone

# Import Response from rest_framework.response (DRF request/response helpers).
from rest_framework.response import Response

# Import TitleSnapshot from catalog.models (our TMDB/normalization layer).
from catalog.models import TitleSnapshot

# Import summary from catalog.normalization (our TMDB/normalization layer).
from catalog.normalization import summary

# Import raw_detail from catalog.services (our TMDB/normalization layer).
from catalog.services import raw_detail

# Import APIError from common.errors (our shared API layer).
from common.errors import APIError

# Import snapshot_page from common.pagination (our shared API layer).
from common.pagination import snapshot_page

# Import Collection, CollectionMembership, GuestCollectionMapping, PublicShare, RecentTitle,
# SavedTitle from library.models (our personal-library layer).
from library.models import (
    Collection,
    CollectionMembership,
    GuestCollectionMapping,
    PublicShare,
    RecentTitle,
    SavedTitle,
)


# Lock this account row inside a transaction so concurrent library changes cannot race past
# quotas.
def lock_user(user):
    # INPUTS TO THIS FUNCTION: user = Django account.
    # Look up a named setting/value or make the indicated get call; the surrounding object
    # determines which.
    get_user_model().objects.select_for_update().get(pk=user.pk)


# Keep media type and TMDB number together; movie 550 and TV 550 are different titles.
def identity(params):
    # INPUTS TO THIS FUNCTION: params = cleaned URL/query values.
    # Return the result to the caller: keep these related values together as a tuple:
    # params['media_type'], params['tmdb_id'].
    return params["media_type"], params["tmdb_id"]


# Reuse a referenced summary when present; otherwise validate a first-time save through TMDB.
def resolve_title(media, tmdb_id):
    # INPUTS TO THIS FUNCTION: media = argument supplied by the caller; tmdb_id = argument
    # supplied by the caller.
    # existing holds an already-present database record or active share URL that can be reused.
    # Next, evaluate this lookup and return one row, or None when no row matches.
    existing = TitleSnapshot.objects.filter(media_type=media, tmdb_id=tmdb_id).first()
    # Enter this branch only when existing. Otherwise execution uses its alternative or continues
    # below.
    if existing:
        # Return the result to the caller: read existing.summary from the indicated object.
        return existing.summary
    # Return the result to the caller: call summary with the inputs shown; its definition explains
    # the checks, side effects and return value.
    return summary(raw_detail(media, tmdb_id), media)


# Store a title summary only when application data needs to reference that title.
def persist_title(data):
    # INPUTS TO THIS FUNCTION: data = validated JSON.
    # Set (row, _): reuse a matching row or insert one; the second returned value says whether it
    # was newly created.
    row, _ = TitleSnapshot.objects.get_or_create(
        media_type=data["media_type"],
        tmdb_id=data["tmdb_id"],
        defaults={"summary": data, "genre_keys": [g["key"] for g in data["genres"]]},
    )
    # Return the result to the caller: reuse row, which was prepared earlier in this function.
    return row


# Copy the stored card and mark old metadata as stale without deleting the user saved item.
def stored_summary(title):
    # INPUTS TO THIS FUNCTION: title = argument supplied by the caller.
    # Set result: make a dictionary copy so changes here need not mutate the caller dictionary.
    result = dict(title.summary)
    # Enter this branch only when timezone.now() - title.fetched_at > timedelta(hours=6).
    # Otherwise execution uses its alternative or continues below.
    if timezone.now() - title.fetched_at > timedelta(hours=6):
        # Set result['metadata_status']: use the fixed value 'stale'.
        result["metadata_status"] = "stale"
    # Return the result to the caller: reuse result, which was prepared earlier in this function.
    return result


# Combine a title card with this account watched state and save/watch timestamps.
def saved_data(row):
    # INPUTS TO THIS FUNCTION: row = argument supplied by the caller.
    # Return this named-field dictionary; API handlers turn it into JSON, while helper callers use
    # it directly.
    return {
        # The normalized card or title reference used here; the surrounding schema distinguishes a
        # string title from a nested card.
        "title": stored_summary(row.title),
        "watched": row.watched,
        # The saved-row creation time, preserved during account merges when the account row
        # already exists.
        "saved_at": row.saved_at.isoformat(),
        # The time a title became watched; null when the watched flag is false.
        "watched_at": row.watched_at.isoformat() if row.watched_at else None,
    }


# Read this account saved rows with their title data in the same ORM query.
def saved_rows(user):
    # INPUTS TO THIS FUNCTION: user = Django account.
    # Return the result to the caller: call list with the inputs shown; its definition explains
    # the checks, side effects and return value.
    return list(
        SavedTitle.objects.filter(user=user)
        .select_related("title")
        .order_by("-saved_at", "title__media_type", "title__tmdb_id")
    )


# Reuse an existing saved row or create one after checking the account save limit.
def ensure_saved(user, title):
    # INPUTS TO THIS FUNCTION: user = Django account; title = argument supplied by the caller.
    # existing holds an already-present database record or active share URL that can be reused.
    # Next, evaluate this lookup and return one row, or None when no row matches.
    existing = SavedTitle.objects.filter(user=user, title=title).first()
    # Enter this branch only when existing. Otherwise execution uses its alternative or continues
    # below.
    if existing:
        # Return the result to the caller: reuse existing, which was prepared earlier in this
        # function.
        return existing
    # Enter this branch only when SavedTitle.objects.filter(user=user).count() >= 5000. Otherwise
    # execution uses its alternative or continues below.
    if SavedTitle.objects.filter(user=user).count() >= 5000:
        # Stop this action with safe API error 'account_limit' (HTTP 409). The common handler
        # builds its JSON envelope.
        raise APIError("account_limit", "Saved title limit reached.", 409)
    # Return the result to the caller: insert a new row and receive the created model object.
    return SavedTitle.objects.create(user=user, title=title)


# List this account saved titles, applying watched/media/order filters before pagination.
def library(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    def fetch():
        # Set rows: call saved_rows with the inputs shown; its definition explains the checks,
        # side effects and return value.
        rows = saved_rows(request.user)
        # Enter this branch only when 'watched' in params. Otherwise execution uses its
        # alternative or continues below.
        if "watched" in params:
            # Set rows: build a list for each r in rows; keep only entries passing r.watched ==
            # params['watched'].
            rows = [r for r in rows if r.watched == params["watched"]]
        # Enter this branch only when 'media_type' in params. Otherwise execution uses its
        # alternative or continues below.
        if "media_type" in params:
            # Set rows: build a list for each r in rows; keep only entries passing
            # r.title.media_type == params['media_type'].
            rows = [r for r in rows if r.title.media_type == params["media_type"]]
        # Enter this branch only when params.get('sort') == 'title_asc'. Otherwise execution uses
        # its alternative or continues below.
        if params.get("sort") == "title_asc":
            # Reorder the existing list using this key; reverse=true means descending.
            rows.sort(
                key=lambda r: (
                    r.title.summary["title"].casefold(),
                    r.title.media_type,
                    r.title.tmdb_id,
                )
            )
        # Return the result to the caller: build a list for each r in rows.
        return [saved_data(r) for r in rows]

    # Return the result to the caller: call snapshot_page with the inputs shown; its definition
    # explains the checks, side effects and return value.
    return snapshot_page(request, params, fetch, f"user:{request.user.pk}")


# Handle save/watch updates or explicit unsave; related membership changes share the same
# transaction.
def saved_title(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # Set (media, tmdb_id): call identity with the inputs shown; its definition explains the
    # checks, side effects and return value.
    media, tmdb_id = identity(params)
    # resolved holds validated title summaries keyed by composite identity; metadata resolution
    # happens before guest-account writes. Next, choose None when request.method == 'DELETE';
    # otherwise use resolve_title(media, tmdb_id).
    resolved = None if request.method == "DELETE" else resolve_title(media, tmdb_id)
    # Treat this group of related database writes as one unit: all commit or all roll back.
    # Start an atomic write boundary. Leaving normally commits it; an exception rolls back this
    # block changes.
    with transaction.atomic():
        # Serializing this owner changes prevents simultaneous requests from bypassing quotas or
        # merge rules.
        # Call lock_user with the inputs shown; its definition explains the checks, side effects
        # and return value.
        lock_user(request.user)
        # Enter this branch only when request.method == 'DELETE'. Otherwise execution uses its
        # alternative or continues below.
        if request.method == "DELETE":
            # affected holds collections containing the saved row being removed, whose update time
            # needs refreshing. Next, construct a Django QuerySet restricted to the conditions
            # shown; it remains lazy until evaluated.
            affected = Collection.objects.filter(
                user=request.user,
                memberships__saved_title__title__media_type=media,
                memberships__saved_title__title__tmdb_id=tmdb_id,
            )
            # Write these fields directly on the matching rows through the orm.
            affected.update(updated_at=timezone.now())
            # Delete the selected row(s), applying their configured related-row deletion rules.
            SavedTitle.objects.filter(
                user=request.user, title__media_type=media, title__tmdb_id=tmdb_id
            ).delete()
            # Return the result to the caller: call Response with the inputs shown; its definition
            # explains the checks, side effects and return value.
            return Response(status=204)
        # title holds a referenced title record or normalized card; this is deliberately separate
        # from an owner SavedTitle row. Next, call persist_title with the inputs shown; its
        # definition explains the checks, side effects and return value.
        title = persist_title(resolved)
        # row holds the current database object being read or changed; its model is identified by
        # the query/constructor below. Next, call ensure_saved with the inputs shown; its
        # definition explains the checks, side effects and return value.
        row = ensure_saved(request.user, title)
        # watched holds the new watched boolean requested for a saved title. Next, read the entry
        # indexed by 'watched' from data.
        watched = data["watched"]
        # Enter this branch only when watched and (not row.watched). Otherwise execution uses its
        # alternative or continues below.
        if watched and not row.watched:
            # Set row.watched_at: call timezone.now with the inputs shown; its definition explains
            # the checks, side effects and return value.
            row.watched_at = timezone.now()
        # Enter this branch only when not watched. Otherwise execution uses its alternative or
        # continues below.
        elif not watched:
            # Set row.watched_at: use None to represent no known value (JSON null at the API
            # boundary).
            row.watched_at = None
        # Set row.watched: reuse watched, which was prepared earlier in this function.
        row.watched = watched
        # Write this model object changes to the database; update_fields, when present, limits the
        # written columns.
        row.save()
        # Return the result to the caller: call saved_data with the inputs shown; its definition
        # explains the checks, side effects and return value.
        return saved_data(row)


# Trim the collection label and require a usable name of at most eighty characters.
def collection_name(name):
    # INPUTS TO THIS FUNCTION: name = argument supplied by the caller.
    # name holds a display name or field label; collection names are trimmed and checked for
    # allowed length. Next, call name.strip with the inputs shown; its definition explains the
    # checks, side effects and return value.
    name = name.strip()
    # Enter this branch only when not name or len(name) > 80. Otherwise execution uses its
    # alternative or continues below.
    if not name or len(name) > 80:
        # Stop this action with safe API error 'validation_error' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError("validation_error", "Collection name must contain 1–80 characters.")
    # Return the result to the caller: reuse name, which was prepared earlier in this function.
    return name


# Find a collection belonging to this account; prevent writes to computed automatic groups.
def owned_collection(user, collection_id, mutable=False):
    # Computed collection IDs are read-only labels, not UUID rows that can be edited.
    # INPUTS TO THIS FUNCTION: user = Django account; collection_id = argument supplied by the
    # caller; mutable = argument supplied by the caller.
    # Enter this branch only when collection_id.startswith('auto:'). Otherwise execution uses its
    # alternative or continues below.
    if collection_id.startswith("auto:"):
        # Enter this branch only when mutable. Otherwise execution uses its alternative or
        # continues below.
        if mutable:
            # Stop this action with safe API error 'immutable_collection' (HTTP 403). The common
            # handler builds its JSON envelope.
            raise APIError("immutable_collection", "Automatic collections are read-only.", 403)
        # Return the result to the caller: use None to represent no known value (JSON null at the
        # API boundary).
        return None
    # Attempt this block; the following except branches handle expected failures without
    # continuing the success path.
    try:
        # Call uuid.uuid with the inputs shown; its definition explains the checks, side effects
        # and return value.
        uuid.UUID(collection_id)
    # Handle ValueError here. The original exception is not automatically safe to expose to the
    # client.
    except ValueError:
        # Stop this action with safe API error 'not_found' (HTTP 404). The common handler builds
        # its JSON envelope.
        raise APIError("not_found", "Collection not found.", 404) from None
    # row holds the current database object being read or changed; its model is identified by the
    # query/constructor below. Next, evaluate this lookup and return one row, or None when no row
    # matches.
    row = Collection.objects.filter(pk=collection_id, user=user).select_related("share").first()
    # Enter this branch only when not row. Otherwise execution uses its alternative or continues
    # below.
    if not row:
        # Stop this action with safe API error 'not_found' (HTTP 404). The common handler builds
        # its JSON envelope.
        raise APIError("not_found", "Collection not found.", 404)
    # Return the result to the caller: reuse row, which was prepared earlier in this function.
    return row


# Create the token encryption helper from a separate environment key; fail safely if it is
# missing.
def cipher():
    # Attempt this block; the following except branches handle expected failures without
    # continuing the success path.
    try:
        # Return the result to the caller: call Fernet with the inputs shown; its definition
        # explains the checks, side effects and return value.
        return Fernet(settings.SHARE_TOKEN_ENCRYPTION_KEY.encode())
    # Handle (ValueError, TypeError) here. The original exception is not automatically safe to
    # expose to the client.
    except (ValueError, TypeError):
        # Stop this action with safe API error 'service_unavailable' (HTTP 503). The common
        # handler builds its JSON envelope.
        raise APIError("service_unavailable", "Share encryption is not configured.", 503) from None


# Build a React share-page URL using the configured, valid frontend origin.
def share_url(token):
    # INPUTS TO THIS FUNCTION: token = argument supplied by the caller.
    # origin holds the configured public React origin used to generate human-facing share URLs.
    # Next, read settings.FRONTEND_PUBLIC_ORIGIN from the indicated object.
    origin = settings.FRONTEND_PUBLIC_ORIGIN
    # parsed holds URL components checked before a public origin is trusted for link generation.
    # Next, call urlsplit with the inputs shown; its definition explains the checks, side effects
    # and return value.
    parsed = urlsplit(origin)
    # Enter this branch only when not parsed.hostname or parsed.username or parsed.password or
    # (parsed.path not in ('', '/')) or (parsed.scheme not in (('http', 'https') if settings.DEBUG
    # else ('https',))). Otherwise execution uses its alternative or continues below.
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.scheme not in (("http", "https") if settings.DEBUG else ("https",))
    ):
        # Stop this action with safe API error 'service_unavailable' (HTTP 503). The common
        # handler builds its JSON envelope.
        raise APIError("service_unavailable", "Public frontend origin is not configured.", 503)
    # Return the result to the caller: calculate origin.rstrip('/') + '/shared/' + token from the
    # intermediate values already prepared.
    return origin.rstrip("/") + "/shared/" + token


# Recover the active owner-visible share link from its encrypted token, not from the one-way
# hash.
def active_share(row):
    # INPUTS TO THIS FUNCTION: row = argument supplied by the caller.
    # Attempt this block; the following except branches handle expected failures without
    # continuing the success path.
    try:
        # share holds the stored public-share state; the recoverable token stays encrypted at
        # rest. Next, read row.share from the indicated object.
        share = row.share
    # Handle PublicShare.DoesNotExist here. The original exception is not automatically safe to
    # expose to the client.
    except PublicShare.DoesNotExist:
        # Return the result to the caller: use None to represent no known value (JSON null at the
        # API boundary).
        return None
    # Enter this branch only when not share.enabled. Otherwise execution uses its alternative or
    # continues below.
    if not share.enabled:
        # Return the result to the caller: use None to represent no known value (JSON null at the
        # API boundary).
        return None
    # Attempt this block; the following except branches handle expected failures without
    # continuing the success path.
    try:
        # Set token: convert bytes back into text after decryption or another bytes-producing
        # operation.
        token = cipher().decrypt(share.encrypted_token.encode()).decode()
    # Handle InvalidToken here. The original exception is not automatically safe to expose to the
    # client.
    except InvalidToken:
        # Stop this action with safe API error 'service_unavailable' (HTTP 503). The common
        # handler builds its JSON envelope.
        raise APIError(
            "service_unavailable", "Share key requires operator attention.", 503
        ) from None
    # Return the result to the caller: call share_url with the inputs shown; its definition
    # explains the checks, side effects and return value.
    return share_url(token)


# Build a collection card with its item count and current owner-visible sharing state.
def collection_data(row, count=None):
    # INPUTS TO THIS FUNCTION: row = argument supplied by the caller; count = argument supplied by
    # the caller.
    # url holds the complete public navigation URL built from the approved configured origin.
    # Next, call active_share with the inputs shown; its definition explains the checks, side
    # effects and return value.
    url = active_share(row)
    # Return this named-field dictionary; API handlers turn it into JSON, while helper callers use
    # it directly.
    return {
        "id": str(row.pk),
        "kind": "custom",
        "name": row.name,
        # Number of members in this collection/group, not all titles in the catalogue.
        "item_count": count if count is not None else row.memberships.count(),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        # Whether this custom collection currently has an active public capability.
        "sharing_enabled": bool(url),
        # Owner-visible React sharing-page link; never a raw Django JSON endpoint URL.
        "share_url": url,
    }


# Group saved rows by genre, decade, rating, media type and watched state without inserting
# collection rows.
def automatic(user):
    # Build automatic groups in Python from saved rows; this does not create Collection records.
    # INPUTS TO THIS FUNCTION: user = Django account.
    # groups holds temporary computed collections; adding to this dictionary does not insert
    # Collection rows. Next, call defaultdict with the inputs shown; its definition explains the
    # checks, side effects and return value.
    groups = defaultdict(list)
    # Repeat the following block for each row from saved_rows(user). Each iteration handles that
    # one item/pair.
    for row in saved_rows(user):
        # title holds a referenced title record or normalized card; this is deliberately separate
        # from an owner SavedTitle row. Next, read row.title.summary from the indicated object.
        title = row.title.summary
        # Repeat the following block for each genre from row.title.genre_keys. Each iteration
        # handles that one item/pair.
        for genre in row.title.genre_keys:
            # Add one item at the end of this list.
            groups[f"auto:genre:{genre}"].append(row)
        # year holds the known release/first-air year; unknown years do not belong in a decade
        # group. Next, look up a named setting/value or make the indicated GET call; the
        # surrounding object determines which.
        year = title.get("year")
        # Enter this branch only when year. Otherwise execution uses its alternative or continues
        # below.
        if year:
            # Add one item at the end of this list.
            groups[f"auto:decade:{year // 10 * 10}"].append(row)
        # Enter this branch only when title.get('rating') is not None and title['rating'] >= 8.
        # Otherwise execution uses its alternative or continues below.
        if title.get("rating") is not None and title["rating"] >= 8:
            # Add one item at the end of this list.
            groups["auto:highly-rated"].append(row)
        # Add one item at the end of this list.
        groups["auto:movies" if row.title.media_type == "movie" else "auto:tv"].append(row)
        # Enter this branch only when row.watched. Otherwise execution uses its alternative or
        # continues below.
        if row.watched:
            # Add one item at the end of this list.
            groups["auto:watched"].append(row)
    # Return the result to the caller: reuse groups, which was prepared earlier in this function.
    return groups


# Describe a computed group using the same response shape as a custom collection.
def auto_data(key, rows):
    # INPUTS TO THIS FUNCTION: key = argument supplied by the caller; rows = argument supplied by
    # the caller.
    # name holds a display name or field label; collection names are trimmed and checked for
    # allowed length. Next, look up a named setting/value or make the indicated GET call; the
    # surrounding object determines which.
    name = {
        "auto:movies": "Movies",
        "auto:tv": "TV Series",
        "auto:highly-rated": "Highly Rated",
        "auto:watched": "Watched",
    }.get(key)
    # Enter this branch only when key.startswith('auto:genre:'). Otherwise execution uses its
    # alternative or continues below.
    if key.startswith("auto:genre:"):
        # name holds a display name or field label; collection names are trimmed and checked for
        # allowed length. Next, call key.split(':')[-1].replace('-', ' ').title with the inputs
        # shown; its definition explains the checks, side effects and return value.
        name = key.split(":")[-1].replace("-", " ").title()
    # Enter this branch only when key.startswith('auto:decade:'). Otherwise execution uses its
    # alternative or continues below.
    elif key.startswith("auto:decade:"):
        # name holds a display name or field label; collection names are trimmed and checked for
        # allowed length. Next, calculate key.split(':')[-1] + 's' from the intermediate values
        # already prepared.
        name = key.split(":")[-1] + "s"
    # Return this named-field dictionary; API handlers turn it into JSON, while helper callers use
    # it directly.
    return {
        "id": key,
        "kind": "automatic",
        "name": name or key,
        # Number of members in this collection/group, not all titles in the catalogue.
        "item_count": len(rows),
        "created_at": None,
        "updated_at": None,
        # Whether this custom collection currently has an active public capability.
        "sharing_enabled": False,
        # Owner-visible React sharing-page link; never a raw Django JSON endpoint URL.
        "share_url": None,
    }


# Create a custom collection, or list custom and computed collections for the current account.
def collections(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # Enter this branch only when request.method == 'POST'. Otherwise execution uses its
    # alternative or continues below.
    if request.method == "POST":
        # name holds a display name or field label; collection names are trimmed and checked for
        # allowed length. Next, call collection_name with the inputs shown; its definition
        # explains the checks, side effects and return value.
        name = collection_name(data["name"])
        # Start an atomic write boundary. Leaving normally commits it; an exception rolls back
        # this block changes.
        with transaction.atomic():
            # Call lock_user with the inputs shown; its definition explains the checks, side
            # effects and return value.
            lock_user(request.user)
            # Enter this branch only when Collection.objects.filter(user=request.user).count() >=
            # 100. Otherwise execution uses its alternative or continues below.
            if Collection.objects.filter(user=request.user).count() >= 100:
                # Stop this action with safe API error 'account_limit' (HTTP 409). The common
                # handler builds its JSON envelope.
                raise APIError("account_limit", "Collection limit reached.", 409)
            # row holds the current database object being read or changed; its model is identified
            # by the query/constructor below. Next, insert a new row and receive the created model
            # object.
            row = Collection.objects.create(user=request.user, name=name)
        # Return the result to the caller: call Response with the inputs shown; its definition
        # explains the checks, side effects and return value.
        return Response(collection_data(row), status=201)

    def fetch():
        # Set rows: specify ordering for the QuerySet; a leading minus means descending order.
        rows = (
            Collection.objects.filter(user=request.user)
            .select_related("share")
            .annotate(total=Count("memberships"))
            .order_by("-updated_at", "id")
        )
        # Set result: build a list for each row in rows.
        result = [collection_data(row, row.total) for row in rows]
        # Add to result using build a list for each (key, values) in
        # sorted(automatic(request.user).items()).
        result += [
            auto_data(key, values) for key, values in sorted(automatic(request.user).items())
        ]
        # Return the result to the caller: reuse result, which was prepared earlier in this
        # function.
        return result

    # Return the result to the caller: call snapshot_page with the inputs shown; its definition
    # explains the checks, side effects and return value.
    return snapshot_page(request, params, fetch, f"user:{request.user.pk}")


# Read one permitted collection with its items, or rename/delete an owned custom collection.
def collection_detail(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # Set key: read the entry indexed by 'collection_id' from params.
    key = params["collection_id"]
    # Enter this branch only when request.method != 'GET'. Otherwise execution uses its
    # alternative or continues below.
    if request.method != "GET":
        # Start an atomic write boundary. Leaving normally commits it; an exception rolls back
        # this block changes.
        with transaction.atomic():
            # Call lock_user with the inputs shown; its definition explains the checks, side
            # effects and return value.
            lock_user(request.user)
            # row holds the current database object being read or changed; its model is identified
            # by the query/constructor below. Next, call owned_collection with the inputs shown;
            # its definition explains the checks, side effects and return value.
            row = owned_collection(request.user, key, mutable=True)
            # Enter this branch only when request.method == 'DELETE'. Otherwise execution uses its
            # alternative or continues below.
            if request.method == "DELETE":
                # Write these fields directly on the matching rows through the orm.
                GuestCollectionMapping.objects.filter(collection=row).update(
                    deleted_at=timezone.now()
                )
                # Delete the selected row(s), applying their configured related-row deletion
                # rules.
                row.delete()
                # Return the result to the caller: call Response with the inputs shown; its
                # definition explains the checks, side effects and return value.
                return Response(status=204)
            # Set row.name: call collection_name with the inputs shown; its definition explains
            # the checks, side effects and return value.
            row.name = collection_name(data["name"])
            # Write this model object changes to the database; update_fields, when present, limits
            # the written columns.
            row.save()
            # Return the result to the caller: call collection_data with the inputs shown; its
            # definition explains the checks, side effects and return value.
            return collection_data(row)
    # row holds the current database object being read or changed; its model is identified by the
    # query/constructor below. Next, call owned_collection with the inputs shown; its definition
    # explains the checks, side effects and return value.
    row = owned_collection(request.user, key)
    # Enter this branch only when row is None. Otherwise execution uses its alternative or
    # continues below.
    if row is None:
        # groups holds temporary computed collections; adding to this dictionary does not insert
        # Collection rows. Next, call automatic with the inputs shown; its definition explains the
        # checks, side effects and return value.
        groups = automatic(request.user)
        # Enter this branch only when key not in groups. Otherwise execution uses its alternative
        # or continues below.
        if key not in groups:
            # Stop this action with safe API error 'not_found' (HTTP 404). The common handler
            # builds its JSON envelope.
            raise APIError("not_found", "Collection not found.", 404)
        # Set rows: read the entry indexed by key from groups.
        rows = groups[key]
        # value holds a value being compared to a filter, or the collection summary returned next
        # to its items. Next, call auto_data with the inputs shown; its definition explains the
        # checks, side effects and return value.
        value = auto_data(key, rows)

        def items():
            # Return the result to the caller: build a list for each r in rows.
            return [{"title": stored_summary(r.title), "added_at": None} for r in rows]
    else:
        # value holds a value being compared to a filter, or the collection summary returned next
        # to its items. Next, call collection_data with the inputs shown; its definition explains
        # the checks, side effects and return value.
        value = collection_data(row)

        def items():
            # Return the result to the caller: call membership_data with the inputs shown; its
            # definition explains the checks, side effects and return value.
            return membership_data(row)

    # page holds the requested one-based page number. Next, call snapshot_page with the inputs
    # shown; its definition explains the checks, side effects and return value.
    page = snapshot_page(request, params, items, f"user:{request.user.pk}:collection:{key}")
    # Return this named-field dictionary; API handlers turn it into JSON, while helper callers use
    # it directly.
    return {"collection": value, "items": page}


# Read collection members and their title summaries in a predictable order.
def membership_data(collection):
    # INPUTS TO THIS FUNCTION: collection = argument supplied by the caller.
    # Return the result to the caller: build a list for each r in
    # collection.memberships.select_related('saved_title__title').order_by('-added_at',
    # 'saved_title__title__media_type', 'saved_title__title__tmdb_id').
    return [
        {"title": stored_summary(r.saved_title.title), "added_at": r.added_at.isoformat()}
        for r in collection.memberships.select_related("saved_title__title").order_by(
            "-added_at", "saved_title__title__media_type", "saved_title__title__tmdb_id"
        )
    ]


# Add/remove one title in an owned custom collection; adding may save it, removing does not
# unsave it.
def membership(request, params, data):
    # Ownership before external lookup prevents another user's UUID acting as a probe.
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # Call owned_collection with the inputs shown; its definition explains the checks, side
    # effects and return value.
    owned_collection(request.user, params["collection_id"], mutable=True)
    # resolved holds validated title summaries keyed by composite identity; metadata resolution
    # happens before guest-account writes. Next, choose resolve_title(*identity(params)) when
    # request.method == 'PUT'; otherwise use None.
    resolved = resolve_title(*identity(params)) if request.method == "PUT" else None
    # Treat this group of related database writes as one unit: all commit or all roll back.
    # Start an atomic write boundary. Leaving normally commits it; an exception rolls back this
    # block changes.
    with transaction.atomic():
        # Serializing this owner changes prevents simultaneous requests from bypassing quotas or
        # merge rules.
        # Call lock_user with the inputs shown; its definition explains the checks, side effects
        # and return value.
        lock_user(request.user)
        # row holds the current database object being read or changed; its model is identified by
        # the query/constructor below. Next, call owned_collection with the inputs shown; its
        # definition explains the checks, side effects and return value.
        row = owned_collection(request.user, params["collection_id"], mutable=True)
        # Enter this branch only when request.method == 'DELETE'. Otherwise execution uses its
        # alternative or continues below.
        if request.method == "DELETE":
            # Delete the selected row(s), applying their configured related-row deletion rules.
            row.memberships.filter(
                saved_title__title__media_type=params["media_type"],
                saved_title__title__tmdb_id=params["tmdb_id"],
            ).delete()
            # Write this model object changes to the database; update_fields, when present, limits
            # the written columns.
            row.save(update_fields=["updated_at"])
            # Return the result to the caller: call Response with the inputs shown; its definition
            # explains the checks, side effects and return value.
            return Response(status=204)
        # title holds a referenced title record or normalized card; this is deliberately separate
        # from an owner SavedTitle row. Next, call persist_title with the inputs shown; its
        # definition explains the checks, side effects and return value.
        title = persist_title(resolved)
        # saved holds an account SavedTitle row or the guest saved-row list, depending on the
        # current workflow. Next, call ensure_saved with the inputs shown; its definition explains
        # the checks, side effects and return value.
        saved = ensure_saved(request.user, title)
        # existing holds an already-present database record or active share URL that can be
        # reused. Next, evaluate this lookup and return one row, or None when no row matches.
        existing = row.memberships.filter(saved_title=saved).first()
        # Enter this branch only when not existing and row.memberships.count() >= 500. Otherwise
        # execution uses its alternative or continues below.
        if not existing and row.memberships.count() >= 500:
            # Stop this action with safe API error 'collection_limit' (HTTP 409). The common
            # handler builds its JSON envelope.
            raise APIError("collection_limit", "Collection item limit reached.", 409)
        # member holds the one collection-to-saved-title relationship being created or reused.
        # Next, evaluate existing or CollectionMembership.objects.create(collection=row,
        # saved_title=saved).
        member = existing or CollectionMembership.objects.create(collection=row, saved_title=saved)
        # Write this model object changes to the database; update_fields, when present, limits the
        # written columns.
        row.save(update_fields=["updated_at"])
        # Return this named-field dictionary; API handlers turn it into JSON, while helper callers
        # use it directly.
        return {"title": stored_summary(title), "added_at": member.added_at.isoformat()}


# Enable or revoke an owned collection capability; repeated enable reuses the active link.
def sharing(request, params, data):
    # Treat this group of related database writes as one unit: all commit or all roll back.
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # Start an atomic write boundary. Leaving normally commits it; an exception rolls back this
    # block changes.
    with transaction.atomic():
        # Serializing this owner changes prevents simultaneous requests from bypassing quotas or
        # merge rules.
        # Call lock_user with the inputs shown; its definition explains the checks, side effects
        # and return value.
        lock_user(request.user)
        # row holds the current database object being read or changed; its model is identified by
        # the query/constructor below. Next, call owned_collection with the inputs shown; its
        # definition explains the checks, side effects and return value.
        row = owned_collection(request.user, params["collection_id"], mutable=True)
        # Enter this branch only when request.method == 'DELETE'. Otherwise execution uses its
        # alternative or continues below.
        if request.method == "DELETE":
            # Write these fields directly on the matching rows through the orm.
            PublicShare.objects.filter(collection=row).update(
                enabled=False, revoked_at=timezone.now()
            )
            # Return the result to the caller: call Response with the inputs shown; its definition
            # explains the checks, side effects and return value.
            return Response(status=204)
        # existing holds an already-present database record or active share URL that can be
        # reused. Next, call active_share with the inputs shown; its definition explains the
        # checks, side effects and return value.
        existing = active_share(row)
        # Enter this branch only when existing. Otherwise execution uses its alternative or
        # continues below.
        if existing:
            # Return this named-field dictionary; API handlers turn it into JSON, while helper
            # callers use it directly.
            return {"enabled": True, "url": existing}
        # Set token: generate cryptographically strong random URL-safe text, not a predictable
        # sequence.
        token = secrets.token_urlsafe(32)
        # url holds the complete public navigation URL built from the approved configured origin.
        # Next, call share_url with the inputs shown; its definition explains the checks, side
        # effects and return value.
        url = share_url(token)
        # Update a matching row or insert one; receive the row and a created/not-created flag.
        PublicShare.objects.update_or_create(
            collection=row,
            defaults={
                "enabled": True,
                "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                "encrypted_token": cipher().encrypt(token.encode()).decode(),
                "revoked_at": None,
            },
        )
        # Return this named-field dictionary; API handlers turn it into JSON, while helper callers
        # use it directly.
        return {"enabled": True, "url": url}


# Check the public capability on every request, then return collection items without private
# account fields.
def shared(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # Set token: read the entry indexed by 'token' from params.
    token = params["token"]
    # Enter this branch only when not re.fullmatch('[A-Za-z0-9_-]{43,128}', token). Otherwise
    # execution uses its alternative or continues below.
    if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", token):
        # Stop this action with safe API error 'not_found' (HTTP 404). The common handler builds
        # its JSON envelope.
        raise APIError("not_found", "Collection not found.", 404)
    # row holds the current database object being read or changed; its model is identified by the
    # query/constructor below. Next, evaluate this lookup and return one row, or None when no row
    # matches.
    row = (
        PublicShare.objects.filter(
            token_hash=hashlib.sha256(token.encode()).hexdigest(), enabled=True
        )
        .select_related("collection")
        .first()
    )
    # Enter this branch only when not row. Otherwise execution uses its alternative or continues
    # below.
    if not row:
        # Stop this action with safe API error 'not_found' (HTTP 404). The common handler builds
        # its JSON envelope.
        raise APIError("not_found", "Collection not found.", 404)
    # A cached list must never let a revoked public link continue to work.
    # Capability is verified on EVERY page, before accessing any cached snapshot.
    # page holds the requested one-based page number. Next, call snapshot_page with the inputs
    # shown; its definition explains the checks, side effects and return value.
    page = snapshot_page(
        request, params, lambda: membership_data(row.collection), f"share:{row.pk}:{row.token_hash}"
    )
    # Return this named-field dictionary; API handlers turn it into JSON, while helper callers use
    # it directly.
    return {"name": row.collection.name, "items": page}


# Read the newest explicitly explored titles; simply opening an API list does not record
# history.
def recent(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    def fetch():
        # Return the result to the caller: build a list for each r in RecentTitle.objects.filter(u
        # ser=request.user).select_related('title').order_by('-explored_at', 'title__media_type',
        # 'title__tmdb_id')[:50].
        return [
            {"title": stored_summary(r.title), "explored_at": r.explored_at.isoformat()}
            for r in RecentTitle.objects.filter(user=request.user)
            .select_related("title")
            .order_by("-explored_at", "title__media_type", "title__tmdb_id")[:50]
        ]

    # Return the result to the caller: call snapshot_page with the inputs shown; its definition
    # explains the checks, side effects and return value.
    return snapshot_page(request, params, fetch, f"user:{request.user.pk}")


# Upsert a deliberate exploration timestamp and retain only the newest fifty references.
def record_recent(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # Set title_data: call resolve_title with the inputs shown; its definition explains the
    # checks, side effects and return value.
    title_data = resolve_title(*identity(params))
    # Treat this group of related database writes as one unit: all commit or all roll back.
    # Start an atomic write boundary. Leaving normally commits it; an exception rolls back this
    # block changes.
    with transaction.atomic():
        # Serializing this owner changes prevents simultaneous requests from bypassing quotas or
        # merge rules.
        # Call lock_user with the inputs shown; its definition explains the checks, side effects
        # and return value.
        lock_user(request.user)
        # title holds a referenced title record or normalized card; this is deliberately separate
        # from an owner SavedTitle row. Next, call persist_title with the inputs shown; its
        # definition explains the checks, side effects and return value.
        title = persist_title(title_data)
        # Set (row, _): update a matching row or insert one; receive the row and a created/not-
        # created flag.
        row, _ = RecentTitle.objects.update_or_create(
            user=request.user, title=title, defaults={"explored_at": timezone.now()}
        )
        # keep holds IDs of the newest fifty history rows; older rows outside this set are pruned.
        # Next, call list with the inputs shown; its definition explains the checks, side effects
        # and return value.
        keep = list(
            RecentTitle.objects.filter(user=request.user)
            .order_by("-explored_at", "pk")
            .values_list("pk", flat=True)[:50]
        )
        # Delete the selected row(s), applying their configured related-row deletion rules.
        RecentTitle.objects.filter(user=request.user).exclude(pk__in=keep).delete()
        # Return this named-field dictionary; API handlers turn it into JSON, while helper callers
        # use it directly.
        return {"title": stored_summary(title), "explored_at": row.explored_at.isoformat()}
