# FILE PURPOSE: Rule-based surprise, mood and saved-title recommendations. No AI model is
# called.
# Import random so the code below can use that module namespace.
import random

# Import defaultdict from collections (the named Python helper module).
from collections import defaultdict

# Import MOODS from catalog.normalization (our TMDB/normalization layer).
from catalog.normalization import MOODS

# Import candidates, locale, validate_filters from catalog.services (our TMDB/normalization
# layer).
from catalog.services import candidates, locale, validate_filters

# Import require_user from common.api (our shared API layer).
from common.api import require_user

# Import APIError from common.errors (our shared API layer).
from common.errors import APIError


# Choose surprise, mood or personalized rules, enforce exclusions and return a small ranked
# selection.
def recommend(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # mode holds the requested recommendation behavior: surprise, mood, or personalized. Next,
    # read the entry indexed by 'mode' from data.
    mode = data["mode"]
    # limit holds the cap chosen for this operation: request rate, page/candidate count, or
    # recommendations. Next, look up a named setting/value or make the indicated GET call; the
    # surrounding object determines which.
    limit = data.get("limit", 1 if mode == "surprise" else 10)
    # mood holds the optional stable mood key; this is different from the display label. Next,
    # look up a named setting/value or make the indicated GET call; the surrounding object
    # determines which.
    mood = data.get("mood")
    # mapping holds the configured genre rules for the chosen mood, or None when no mood matches.
    # Next, call next with the inputs shown; its definition explains the checks, side effects and
    # return value.
    mapping = next((m for m in MOODS if m["key"] == mood), None)
    # Enter this branch only when mode == 'mood' and (not mapping) or (mode != 'mood' and mood) or
    # (mode == 'surprise' and limit != 1). Otherwise execution uses its alternative or continues
    # below.
    if (
        (mode == "mood" and not mapping)
        or (mode != "mood" and mood)
        or (mode == "surprise" and limit != 1)
    ):
        # Stop this action with safe API error 'validation_error' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError("validation_error", "Invalid mode, mood or limit.")
    # Set filters: look up a named setting/value or make the indicated GET call; the surrounding
    # object determines which.
    filters = data.get("filters", {})
    # Call validate_filters with the inputs shown; its definition explains the checks, side
    # effects and return value.
    validate_filters(filters)
    # values holds the chosen locale/region or the converted input values passed to later
    # validation. Next, call locale with the inputs shown; its definition explains the checks,
    # side effects and return value.
    values = locale(request, data)
    # excluded holds composite title identities that must not appear in these recommendations.
    # Next, build a set of distinct values for each x in data.get('exclude', []).
    excluded = {(x["media_type"], x["tmdb_id"]) for x in data.get("exclude", [])}
    # Start each unseen genre at 0.0; adding weight for a new key does not need a separate
    # initialization branch.
    weights = defaultdict(float)
    # basis holds the response label explaining which recommendation rule/fallback was actually
    # used. Next, choose 'random_candidates' when mode == 'surprise'; otherwise use
    # 'mood_mapping'.
    basis = "random_candidates" if mode == "surprise" else "mood_mapping"
    # Enter this branch only when mode == 'personalized'. Otherwise execution uses its alternative
    # or continues below.
    if mode == "personalized":
        # Import SavedTitle from library.models (our personal-library layer).
        from library.models import SavedTitle

        # Call require_user with the inputs shown; its definition explains the checks, side
        # effects and return value.
        require_user(request)
        # Repeat the following block for each saved from
        # SavedTitle.objects.filter(user=request.user).select_related('title'). Each iteration
        # handles that one item/pair.
        for saved in SavedTitle.objects.filter(user=request.user).select_related("title"):
            # Add one value to a set or an absent cache key; sets avoid duplicate values.
            excluded.add((saved.title.media_type, saved.title.tmdb_id))
            # Repeat the following block for each key from saved.title.genre_keys. Each iteration
            # handles that one item/pair.
            for key in saved.title.genre_keys:
                # Increase this saved genre interest by 1.5 if watched, otherwise 1.0. This is a
                # simple rule, not model training.
                weights[key] += 1.5 if saved.watched else 1.0
        # basis holds the response label explaining which recommendation rule/fallback was
        # actually used. Next, choose 'saved_metadata' when weights; otherwise use
        # 'popular_fallback'.
        basis = "saved_metadata" if weights else "popular_fallback"
    # seed holds candidate-generating genres; explicit user filters remain hard constraints
    # afterward. Next, choose mapping['genre_keys'] when mapping; otherwise use sorted(weights,
    # key=lambda k: (-weights[k], k))[:3].
    seed = mapping["genre_keys"] if mapping else sorted(weights, key=lambda k: (-weights[k], k))[:3]
    # Set rows: build a list for each t in candidates(filters, **values, seed_genres=seed); keep
    # only entries passing (t['media_type'], t['tmdb_id']) not in excluded.
    rows = [
        t
        for t in candidates(filters, **values, seed_genres=seed)
        if (t["media_type"], t["tmdb_id"]) not in excluded
    ]
    # A configured mood was selected, so apply its genre predicate as an additional condition.
    if mapping:
        # Set keys: make a set so duplicate entries disappear and membership checks are
        # straightforward.
        keys = set(mapping["genre_keys"])
        # Set rows: build a list for each t in rows; keep only entries passing
        # keys.issubset({g['key'] for g in t['genres']}) if mood == 'family_night' else bool(keys
        # & {g['key'] for g in t['genres']}).
        rows = [
            t
            for t in rows
            if (
                keys.issubset({g["key"] for g in t["genres"]})
                if mood == "family_night"
                else bool(keys & {g["key"] for g in t["genres"]})
            )
        ]
    # Enter this branch only when mode == 'surprise'. Otherwise execution uses its alternative or
    # continues below.
    if mode == "surprise":
        # Sample without replacement; an empty candidate list returns an empty result rather than
        # raising.
        rows = random.sample(rows, min(1, len(rows)))
    # Enter this branch only when mode == 'personalized' and weights. Otherwise execution uses its
    # alternative or continues below.
    elif mode == "personalized" and weights:
        # Normalize against the most-weighted genre so account library size does not directly
        # dominate scores.
        maximum = max(weights.values())
        # Use candidate-relative popularity and a fallback of 1 to avoid division by zero.
        pop_max = max((t["popularity"] for t in rows), default=1) or 1

        # Calculate a recommendation score from genre affinity, TMDB rating and candidate
        # popularity.
        def score(t):
            # INPUTS TO THIS FUNCTION: t = argument supplied by the caller.
            # Set keys: build a list for each g in t['genres'].
            keys = [g["key"] for g in t["genres"]]
            # affinity holds the mean normalized interest weight across the candidate genres.
            # Next, calculate sum((weights[k] / maximum for k in keys)) / max(1, len(keys)) from
            # the intermediate values already prepared.
            affinity = sum(weights[k] / maximum for k in keys) / max(1, len(keys))
            # Score is 70% genre affinity, 20% scaled TMDB rating and 10% relative popularity;
            # missing rating contributes zero.
            return (
                0.7 * affinity + 0.2 * ((t["rating"] or 0) / 10) + 0.1 * t["popularity"] / pop_max
            )

        # Reorder the existing list using this key; reverse=true means descending.
        rows.sort(key=lambda t: (-score(t), t["media_type"], t["tmdb_id"]))
    else:
        # Reorder the existing list using this key; reverse=true means descending.
        rows.sort(key=lambda t: (-t["popularity"], t["media_type"], t["tmdb_id"]))
    # Return this named-field dictionary; API handlers turn it into JSON, while helper callers use
    # it directly.
    return {
        "mode": mode,
        # Describes the actual recommendation method/fallback used for this result.
        "basis": basis,
        # Version marker for deterministic mood rules, included so caches can change with the
        # rules.
        "mapping_version": "moods-v2",
        # The response list for this page/selection, not necessarily all cached candidates.
        "results": rows[:limit],
        # Optional-section failures that can be displayed without hiding valid core title details.
        "warnings": [],
    }
