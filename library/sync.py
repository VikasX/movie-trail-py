# FILE PURPOSE: Safely merges a submitted guest library into the signed-in account without
# deleting account data.
# LEARNING TIP: read the matching walkthrough in docs/BACKEND_GUIDE.md, then follow the block
# comments below.
# Import hashlib so the code below can use that module namespace.
import hashlib

# Import json so the code below can use that module namespace.
import json

# Import timedelta from datetime (the named Python helper module).
from datetime import timedelta

# Import transaction from django.db (Django framework/database/security helpers).
from django.db import transaction

# Import Q from django.db.models (Django framework/database/security helpers).
from django.db.models import Q

# Import timezone from django.utils (Django framework/database/security helpers).
from django.utils import timezone

# Import parse_datetime from django.utils.dateparse (Django framework/database/security helpers).
from django.utils.dateparse import parse_datetime

# Import TitleSnapshot from catalog.models (our TMDB/normalization layer).
from catalog.models import TitleSnapshot

# Import APIError from common.errors (our shared API layer).
from common.errors import APIError

# Import Collection, CollectionMembership, GuestCollectionMapping, SavedTitle, SyncReceipt from
# library.models (our personal-library layer).
from library.models import (
    Collection,
    CollectionMembership,
    GuestCollectionMapping,
    SavedTitle,
    SyncReceipt,
)

# Import collection_name, lock_user, resolve_title from library.services (our personal-library
# layer).
from library.services import collection_name, lock_user, resolve_title


# Make a tuple identifying a guest title independently of any local database row ID.
def key(value):
    # INPUTS TO THIS FUNCTION: value = item being checked.
    # Return the result to the caller: keep these related values together as a tuple:
    # value['media_type'], value['tmdb_id'].
    return value["media_type"], value["tmdb_id"]


# Check guest-import duplicates, size/count rules and consistent timestamps before database
# writes.
def validate_payload(data):
    # INPUTS TO THIS FUNCTION: data = validated JSON.
    # saved holds an account SavedTitle row or the guest saved-row list, depending on the current
    # workflow. Next, read the entry indexed by 'saved_titles' from data.
    saved = data["saved_titles"]
    # Set collections: read the entry indexed by 'collections' from data.
    collections = data["collections"]
    # Enter this branch only when len({key(v) for v in saved}) != len(saved) or
    # len({c['client_id'] for c in collections}) != len(collections). Otherwise execution uses its
    # alternative or continues below.
    if len({key(v) for v in saved}) != len(saved) or len(
        {c["client_id"] for c in collections}
    ) != len(collections):
        # Stop this action with safe API error 'validation_error' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError("validation_error", "Duplicate title or collection identifiers.")
    # refs holds distinct movie/TV identity pairs that the submitted import refers to. Next, build
    # a set of distinct values for each v in saved.
    refs = {key(v) for v in saved}
    # total holds the total membership count, not merely the number of distinct titles. Next, use
    # the fixed value 0.
    total = 0
    # Repeat the following block for each collection from collections. Each iteration handles that
    # one item/pair.
    for collection in collections:
        # Call collection_name with the inputs shown; its definition explains the checks, side
        # effects and return value.
        collection_name(collection["name"])
        # members holds the title pairs belonging to this one guest collection. Next, build a list
        # for each v in collection['items'].
        members = [key(v) for v in collection["items"]]
        # Enter this branch only when len(set(members)) != len(members). Otherwise execution uses
        # its alternative or continues below.
        if len(set(members)) != len(members):
            # Stop this action with safe API error 'validation_error' (HTTP 400). The common
            # handler builds its JSON envelope.
            raise APIError("validation_error", "Duplicate collection members.")
        # Write these fields directly on the matching rows through the orm.
        refs.update(members)
        # Add to total using count the elements currently in this Python collection.
        total += len(members)
    # Enter this branch only when len(refs) > 500 or total > 2000. Otherwise execution uses its
    # alternative or continues below.
    if len(refs) > 500 or total > 2000:
        # Stop this action with safe API error 'validation_error' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError("validation_error", "Guest import limits exceeded.")
    # Repeat the following block for each row from saved. Each iteration handles that one
    # item/pair.
    for row in saved:
        # saved_at holds the parsed original guest save timestamp, which must include its
        # timezone. Next, parse the submitted timestamp text; validation below checks timezone and
        # consistency.
        saved_at = parse_datetime(row["saved_at"])
        # watched_at holds the parsed guest watch timestamp; its presence must agree with
        # watched=true. Next, choose parse_datetime(row['watched_at']) when row['watched_at'];
        # otherwise use None.
        watched_at = parse_datetime(row["watched_at"]) if row["watched_at"] else None
        # Enter this branch only when not saved_at or timezone.is_naive(saved_at) or (watched_at
        # and timezone.is_naive(watched_at)). Otherwise execution uses its alternative or
        # continues below.
        if (
            not saved_at
            or timezone.is_naive(saved_at)
            or (watched_at and timezone.is_naive(watched_at))
        ):
            # Stop this action with safe API error 'validation_error' (HTTP 400). The common
            # handler builds its JSON envelope.
            raise APIError("validation_error", "Timestamps must include a timezone.")
        # Enter this branch only when bool(watched_at) != row['watched'] or (watched_at and
        # watched_at < saved_at). Otherwise execution uses its alternative or continues below.
        if bool(watched_at) != row["watched"] or (watched_at and watched_at < saved_at):
            # Stop this action with safe API error 'validation_error' (HTTP 400). The common
            # handler builds its JSON envelope.
            raise APIError("validation_error", "Inconsistent watched timestamp.")
        # Enter this branch only when max(saved_at, watched_at or saved_at) > timezone.now() +
        # timedelta(minutes=5). Otherwise execution uses its alternative or continues below.
        if max(saved_at, watched_at or saved_at) > timezone.now() + timedelta(minutes=5):
            # Stop this action with safe API error 'validation_error' (HTTP 400). The common
            # handler builds its JSON envelope.
            raise APIError("validation_error", "Future guest timestamps are not allowed.")
    # Return the result to the caller: reuse refs, which was prepared earlier in this function.
    return refs


# Replay a recent completed import, or reject reuse of its sync ID with changed data.
def receipt_result(user, data, fingerprint):
    # INPUTS TO THIS FUNCTION: user = Django account; data = validated JSON; fingerprint =
    # argument supplied by the caller.
    # existing holds an already-present database record or active share URL that can be reused.
    # Next, evaluate this lookup and return one row, or None when no row matches.
    existing = SyncReceipt.objects.filter(
        user=user, sync_id=data["sync_id"], expires_at__gt=timezone.now()
    ).first()
    # Enter this branch only when existing. Otherwise execution uses its alternative or continues
    # below.
    if existing:
        # Enter this branch only when existing.request_hash != fingerprint. Otherwise execution
        # uses its alternative or continues below.
        if existing.request_hash != fingerprint:
            # Stop this action with safe API error 'idempotency_conflict' (HTTP 409). The common
            # handler builds its JSON envelope.
            raise APIError(
                "idempotency_conflict", "sync_id was already used with different data.", 409
            )
        # Return the result to the caller: read existing.result from the indicated object.
        return existing.result
    # Return the result to the caller: use None to represent no known value (JSON null at the API
    # boundary).
    return None


# Resolve identities first, then atomically merge saves, watched flags, collections, members and
# a retry receipt.
def sync(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # refs holds distinct movie/TV identity pairs that the submitted import refers to. Next, call
    # validate_payload with the inputs shown; its definition explains the checks, side effects and
    # return value.
    refs = validate_payload(data)
    # The sync ID names the attempt; this hash proves a retry contains the same data.
    # fingerprint holds a deterministic hash/input identity; sorting keys makes equivalent
    # dictionaries compare consistently. Next, represent a hash as printable hexadecimal text;
    # this does not reveal its original secret.
    fingerprint = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    # previous holds an already-completed import response that can be replayed without repeating
    # writes. Next, call receipt_result with the inputs shown; its definition explains the checks,
    # side effects and return value.
    previous = receipt_result(request.user, data, fingerprint)
    # This import already completed with the same payload: return its recorded result immediately.
    if previous is not None:
        # Return the result to the caller: reuse previous, which was prepared earlier in this
        # function.
        return previous
    # Resolve identities before opening a write transaction. No partial user data on failure.
    # Fetch already-known movie/TV identities in a batch before requesting missing metadata.
    # predicate holds a combined Django Q expression selecting referenced movies OR referenced TV
    # identities in one batch. Next, combine the two query alternatives or sets with OR/union, as
    # their types determine.
    predicate = Q(media_type="movie", tmdb_id__in=[i for m, i in refs if m == "movie"]) | Q(
        media_type="tv", tmdb_id__in=[i for m, i in refs if m == "tv"]
    )
    # resolved holds validated title summaries keyed by composite identity; metadata resolution
    # happens before guest-account writes. Next, build a lookup dictionary for each row in
    # TitleSnapshot.objects.filter(predicate).
    resolved = {
        (row.media_type, row.tmdb_id): row.summary
        for row in TitleSnapshot.objects.filter(predicate)
    }
    # rejected holds definitively unavailable identities reported back without aborting other
    # accepted import items. Next, build an ordered list of 0 entries.
    rejected = []
    # Only unresolved identities need external validation; network failure occurs before account
    # writes.
    # Repeat the following block for each (media, tmdb_id) from sorted(refs - set(resolved)). Each
    # iteration handles that one item/pair.
    for media, tmdb_id in sorted(refs - set(resolved)):
        # Attempt this block; the following except branches handle expected failures without
        # continuing the success path.
        try:
            # Set resolved[media, tmdb_id]: call resolve_title with the inputs shown; its
            # definition explains the checks, side effects and return value.
            resolved[(media, tmdb_id)] = resolve_title(media, tmdb_id)
        # Handle APIError here. The original exception is not automatically safe to expose to the
        # client.
        except APIError as exc:
            # Enter this branch only when exc.status_code == 404. Otherwise execution uses its
            # alternative or continues below.
            if exc.status_code == 404:
                # Add one item at the end of this list.
                rejected.append(
                    {
                        # The normalized card or title reference used here; the surrounding schema
                        # distinguishes a string title from a nested card.
                        "title": {"media_type": media, "tmdb_id": tmdb_id},
                        "code": "title_unavailable",
                    }
                )
            else:
                # Stop this action with safe API error 'sync_retry_later' (HTTP 503). The common
                # handler builds its JSON envelope.
                raise APIError(
                    "sync_retry_later",
                    "Import metadata is temporarily unavailable; retry the same sync_id.",
                    503,
                    retry_after=30,
                ) from None
    # guest_saved holds a lookup of the submitted guest save state by movie/TV pair. Next, build a
    # lookup dictionary for each row in data['saved_titles'].
    guest_saved = {key(row): row for row in data["saved_titles"]}
    # From here, the guest merge is atomic: quota/error failures undo all of its account writes.
    # Start an atomic write boundary. Leaving normally commits it; an exception rolls back this
    # block changes.
    with transaction.atomic():
        # Call lock_user with the inputs shown; its definition explains the checks, side effects
        # and return value.
        lock_user(request.user)
        # Check again after locking: another request might have completed the same sync while we
        # waited.
        # previous holds an already-completed import response that can be replayed without
        # repeating writes. Next, call receipt_result with the inputs shown; its definition
        # explains the checks, side effects and return value.
        previous = receipt_result(request.user, data, fingerprint)
        # This import already completed with the same payload: return its recorded result
        # immediately.
        if previous is not None:
            # Return the result to the caller: reuse previous, which was prepared earlier in this
            # function.
            return previous
        # Set result: build a dictionary with named fields such as sync_id, saved_created,
        # saved_merged, collections_created, memberships_created, collection_mappings,
        # rejected_titles.
        result = {
            "sync_id": data["sync_id"],
            # How many accepted saved rows were new in this completed import.
            "saved_created": 0,
            # How many accepted identities already had saved rows and were merged/reused.
            "saved_merged": 0,
            # How many new custom collection rows this import created.
            "collections_created": 0,
            # How many previously absent collection-to-saved-title links were inserted.
            "memberships_created": 0,
            # Maps stable guest collection UUIDs to resulting account collection UUIDs.
            "collection_mappings": [],
            # Definitively unavailable identities excluded from this import, not a list of
            # transient network failures.
            "rejected_titles": rejected,
        }
        # existing_saved holds this account existing save rows, indexed by composite title
        # identity. Next, build a lookup dictionary for each r in
        # SavedTitle.objects.filter(user=request.user).select_related('title').
        existing_saved = {
            (r.title.media_type, r.title.tmdb_id): r
            for r in SavedTitle.objects.filter(user=request.user).select_related("title")
        }
        # Enter this branch only when len(existing_saved) + len(set(resolved) -
        # set(existing_saved)) > 5000. Otherwise execution uses its alternative or continues
        # below.
        if len(existing_saved) + len(set(resolved) - set(existing_saved)) > 5000:
            # Stop this action with safe API error 'account_limit' (HTTP 409). The common handler
            # builds its JSON envelope.
            raise APIError("account_limit", "Saved title limit reached.", 409)
        # Set (created_saved, updated_saved): keep these related values together as a tuple: [],
        # [].
        created_saved, updated_saved = [], []
        # now holds one server timestamp shared by related changes in this action. Next, call
        # timezone.now with the inputs shown; its definition explains the checks, side effects and
        # return value.
        now = timezone.now()
        # Insert referenced metadata in a batch, tolerating another account having inserted the
        # same identity.
        # Insert a batch of prepared model objects, reducing database round trips.
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
        # titles holds referenced TitleSnapshot rows indexed by their movie/TV identity pairs.
        # Next, build a lookup dictionary for each row in TitleSnapshot.objects.filter(predicate).
        titles = {
            (row.media_type, row.tmdb_id): row for row in TitleSnapshot.objects.filter(predicate)
        }
        # Repeat the following block for each ref from resolved. Each iteration handles that one
        # item/pair.
        for ref in resolved:
            # guest holds the submitted guest save/collection currently being merged. Next, look
            # up a named setting/value or make the indicated GET call; the surrounding object
            # determines which.
            guest = guest_saved.get(ref)
            # row holds the current database object being read or changed; its model is identified
            # by the query/constructor below. Next, look up a named setting/value or make the
            # indicated GET call; the surrounding object determines which.
            row = existing_saved.get(ref)
            # Enter this branch only when row. Otherwise execution uses its alternative or
            # continues below.
            if row:
                # Add to result['saved_merged'] using use the fixed value 1.
                result["saved_merged"] += 1
                # Merge with watched OR: imported false must never overwrite an account existing
                # true.
                # Enter this branch only when guest and guest['watched'] and (not row.watched).
                # Otherwise execution uses its alternative or continues below.
                if guest and guest["watched"] and not row.watched:
                    # Only upgrade an account false to true in this merge; guest false never
                    # downgrades an existing watched title.
                    row.watched = True
                    # Preserve the guest watched timestamp when this import is what first marks
                    # the account item watched.
                    row.watched_at = parse_datetime(guest["watched_at"])
                    # Mark this existing row changed using the transaction shared server
                    # timestamp.
                    row.updated_at = now
                    # Add one item at the end of this list.
                    updated_saved.append(row)
            else:
                # title holds a referenced title record or normalized card; this is deliberately
                # separate from an owner SavedTitle row. Next, read the entry indexed by ref from
                # titles.
                title = titles[ref]
                # row holds the current database object being read or changed; its model is
                # identified by the query/constructor below. Next, prepare a SavedTitle model
                # object in memory; it is written only by save or bulk_create.
                row = SavedTitle(
                    user=request.user,
                    title=title,
                    watched=bool(guest and guest["watched"]),
                    saved_at=parse_datetime(guest["saved_at"]) if guest else now,
                    watched_at=parse_datetime(guest["watched_at"])
                    if guest and guest["watched"]
                    else None,
                )
                # Add one item at the end of this list.
                created_saved.append(row)
                # Add to result['saved_created'] using use the fixed value 1.
                result["saved_created"] += 1
        # Insert a batch of prepared model objects, reducing database round trips.
        SavedTitle.objects.bulk_create(created_saved)
        # Enter this branch only when updated_saved. Otherwise execution uses its alternative or
        # continues below.
        if updated_saved:
            # Write the listed fields for several existing rows as a batch.
            SavedTitle.objects.bulk_update(updated_saved, ["watched", "watched_at", "updated_at"])
        # existing_saved holds this account existing save rows, indexed by composite title
        # identity. Next, build a lookup dictionary for each r in
        # SavedTitle.objects.filter(user=request.user).select_related('title').
        existing_saved = {
            (r.title.media_type, r.title.tmdb_id): r
            for r in SavedTitle.objects.filter(user=request.user).select_related("title")
        }
        # used_names holds case-folded custom collection names, used to choose a collision-free
        # imported label. Next, build a set of distinct values for each name in
        # Collection.objects.filter(user=request.user).values_list('name', flat=True).
        used_names = {
            name.casefold()
            for name in Collection.objects.filter(user=request.user).values_list("name", flat=True)
        }
        # Repeat the following block for each guest from data['collections']. Each iteration
        # handles that one item/pair.
        for guest in data["collections"]:
            # mapping holds the configured genre rules for the chosen mood, or None when no mood
            # matches. Next, evaluate this lookup and return one row, or None when no row matches.
            mapping = (
                GuestCollectionMapping.objects.filter(
                    user=request.user, guest_id=data["guest_id"], client_id=guest["client_id"]
                )
                .select_related("collection")
                .first()
            )
            # A deleted imported collection is a remembered decision, not a missing row to
            # silently recreate.
            # Enter this branch only when mapping and (mapping.collection is None or
            # mapping.deleted_at). Otherwise execution uses its alternative or continues below.
            if mapping and (mapping.collection is None or mapping.deleted_at):
                # Stop this action with safe API error 'sync_source_deleted' (HTTP 409). The
                # common handler builds its JSON envelope.
                raise APIError(
                    "sync_source_deleted",
                    "An imported collection was deleted. Confirm before importing it again.",
                    409,
                )
            # Enter this branch only when not mapping. Otherwise execution uses its alternative or
            # continues below.
            if not mapping:
                # Enter this branch only when len(used_names) >= 100. Otherwise execution uses its
                # alternative or continues below.
                if len(used_names) >= 100:
                    # Stop this action with safe API error 'account_limit' (HTTP 409). The common
                    # handler builds its JSON envelope.
                    raise APIError("account_limit", "Collection limit reached.", 409)
                # base holds the desired original name, kept so suffix attempts do not repeatedly
                # modify the previous suffix. Next, call collection_name with the inputs shown;
                # its definition explains the checks, side effects and return value.
                base = collection_name(guest["name"])
                # Set (name, suffix): keep these related values together as a tuple: base, 2.
                name, suffix = base, 2
                # Keep both collections when names collide; derive a predictable Imported
                # suffix.
                # Keep trying this block while name.casefold() in used_names. The loop body
                # updates the values used by this condition.
                while name.casefold() in used_names:
                    # tail holds the Imported-number suffix; reserve space so the complete
                    # collection name stays within eighty characters. Next, evaluate f' (Imported
                    # {suffix})'.
                    tail = f" (Imported {suffix})"
                    # name holds a display name or field label; collection names are trimmed and
                    # checked for allowed length. Next, calculate base[:80 - len(tail)] + tail
                    # from the intermediate values already prepared.
                    name = base[: 80 - len(tail)] + tail
                    # Add to suffix using use the fixed value 1.
                    suffix += 1
                # Reserve the chosen name in this in-memory import too, so later collections in
                # the same payload cannot reuse it.
                used_names.add(name.casefold())
                # collection holds the account custom collection matched or created for this guest
                # source. Next, insert a new row and receive the created model object.
                collection = Collection.objects.create(user=request.user, name=name)
                # mapping holds the configured genre rules for the chosen mood, or None when no
                # mood matches. Next, insert a new row and receive the created model object.
                mapping = GuestCollectionMapping.objects.create(
                    user=request.user,
                    guest_id=data["guest_id"],
                    client_id=guest["client_id"],
                    collection=collection,
                )
                # Add to result['collections_created'] using use the fixed value 1.
                result["collections_created"] += 1
            # collection holds the account custom collection matched or created for this guest
            # source. Next, read mapping.collection from the indicated object.
            collection = mapping.collection
            # refs_for_collection holds accepted title identities from this guest collection;
            # rejected identities are excluded. Next, keep the overlap between the two
            # sets/conditions.
            refs_for_collection = {key(r) for r in guest["items"]} & set(resolved)
            # existing_ids holds saved-row IDs already linked to the account collection. Next,
            # make a set so duplicate entries disappear and membership checks are straightforward.
            existing_ids = set(collection.memberships.values_list("saved_title_id", flat=True))
            # Add only memberships absent from this collection; existing memberships are
            # preserved.
            # Set difference removes already-linked saved rows, making membership insertion safe
            # to repeat.
            new_ids = {existing_saved[ref].pk for ref in refs_for_collection} - existing_ids
            # Enter this branch only when len(existing_ids) + len(new_ids) > 500. Otherwise
            # execution uses its alternative or continues below.
            if len(existing_ids) + len(new_ids) > 500:
                # Stop this action with safe API error 'collection_limit' (HTTP 409). The common
                # handler builds its JSON envelope.
                raise APIError("collection_limit", "Collection item limit reached.", 409)
            # Insert a batch of prepared model objects, reducing database round trips.
            CollectionMembership.objects.bulk_create(
                [CollectionMembership(collection=collection, saved_title_id=pk) for pk in new_ids]
            )
            # Add to result['memberships_created'] using count the elements currently in this
            # Python collection.
            result["memberships_created"] += len(new_ids)
            # Write these fields directly on the matching rows through the orm.
            Collection.objects.filter(pk=collection.pk).update(updated_at=now)
            # Add one item at the end of this list.
            result["collection_mappings"].append(
                {"client_id": guest["client_id"], "collection_id": str(collection.pk)}
            )
        # Save the retry receipt in the same transaction as the merged rows.
        # Update a matching row or insert one; receive the row and a created/not-created flag.
        SyncReceipt.objects.update_or_create(
            user=request.user,
            sync_id=data["sync_id"],
            defaults={
                "request_hash": fingerprint,
                "result": result,
                # Time after which this remembered selection/token/receipt must no longer be
                # reused.
                "expires_at": now + timedelta(hours=24),
            },
        )
        # Return the result to the caller: reuse result, which was prepared earlier in this
        # function.
        return result
