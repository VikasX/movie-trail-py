import random
from collections import defaultdict

from catalog.normalization import MOODS
from catalog.services import candidates, locale, validate_filters
from common.api import require_user
from common.errors import APIError


def recommend(request, params, data):
    mode = data["mode"]
    limit = data.get("limit", 1 if mode == "surprise" else 10)
    mood = data.get("mood")
    mapping = next((m for m in MOODS if m["key"] == mood), None)
    if (
        (mode == "mood" and not mapping)
        or (mode != "mood" and mood)
        or (mode == "surprise" and limit != 1)
    ):
        raise APIError("validation_error", "Invalid mode, mood or limit.")
    filters = data.get("filters", {})
    validate_filters(filters)
    values = locale(request, data)
    excluded = {(x["media_type"], x["tmdb_id"]) for x in data.get("exclude", [])}
    weights = defaultdict(float)
    basis = "random_candidates" if mode == "surprise" else "mood_mapping"
    if mode == "personalized":
        from library.models import SavedTitle

        require_user(request)
        for saved in SavedTitle.objects.filter(user=request.user).select_related("title"):
            excluded.add((saved.title.media_type, saved.title.tmdb_id))
            for key in saved.title.genre_keys:
                weights[key] += 1.5 if saved.watched else 1.0
        basis = "saved_metadata" if weights else "popular_fallback"
    seed = mapping["genre_keys"] if mapping else sorted(weights, key=lambda k: (-weights[k], k))[:3]
    rows = [
        t
        for t in candidates(filters, **values, seed_genres=seed)
        if (t["media_type"], t["tmdb_id"]) not in excluded
    ]
    if mapping:
        keys = set(mapping["genre_keys"])
        rows = [
            t
            for t in rows
            if (
                keys.issubset({g["key"] for g in t["genres"]})
                if mood == "family_night"
                else bool(keys & {g["key"] for g in t["genres"]})
            )
        ]
    if mode == "surprise":
        rows = random.sample(rows, min(1, len(rows)))
    elif mode == "personalized" and weights:
        maximum = max(weights.values())
        pop_max = max((t["popularity"] for t in rows), default=1) or 1

        def score(t):
            keys = [g["key"] for g in t["genres"]]
            affinity = sum(weights[k] / maximum for k in keys) / max(1, len(keys))
            return (
                0.7 * affinity + 0.2 * ((t["rating"] or 0) / 10) + 0.1 * t["popularity"] / pop_max
            )

        rows.sort(key=lambda t: (-score(t), t["media_type"], t["tmdb_id"]))
    else:
        rows.sort(key=lambda t: (-t["popularity"], t["media_type"], t["tmdb_id"]))
    return {
        "mode": mode,
        "basis": basis,
        "mapping_version": "moods-v2",
        "results": rows[:limit],
        "warnings": [],
    }
