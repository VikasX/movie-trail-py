from datetime import date, timedelta

from django.core.cache import cache

from catalog.client import TMDBClient
from catalog.normalization import GENRE_KEYS, GENRES, MOODS, image, person, summary, trailers
from common.errors import APIError
from common.pagination import snapshot_page


def metadata_values():
    hit = cache.get("metadata:v2")
    if hit:
        return hit
    client = TMDBClient()
    languages = client.get("configuration/languages", ttl=86400)
    regions = client.get("configuration/countries", ttl=86400)
    if not isinstance(languages, list) or not isinstance(regions, list):
        raise APIError("upstream_invalid", "Invalid provider configuration.", 502)
    result = {
        "genres": [{"key": k, "name": k.replace("-", " ").title()} for k in GENRE_KEYS],
        "languages": [
            {
                "code": language["iso_639_1"],
                "name": language.get("english_name") or language.get("name", ""),
            }
            for language in languages
        ],
        "regions": [
            {"code": r["iso_3166_1"], "name": r.get("english_name") or r.get("native_name", "")}
            for r in regions
        ],
        "moods": MOODS,
        "mood_mapping_version": "moods-v2",
        "attribution": {
            "tmdb_notice": (
                "This product uses the TMDB API but is not endorsed or certified by TMDB."
            ),
            "tmdb_url": "https://www.themoviedb.org",
            "watch_providers": "JustWatch",
        },
    }
    cache.set("metadata:v2", result, 86400)
    return result


def validate_locale(language, region):
    import re

    metadata = metadata_values()
    codes = {language["code"] for language in metadata["languages"]}
    regions = {r["code"] for r in metadata["regions"]}
    if (
        not re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", language)
        or language.split("-")[0] not in codes
        or region not in regions
    ):
        raise APIError("validation_error", "Unsupported language or region.")
    if "-" in language and language.split("-")[1] not in regions:
        raise APIError("validation_error", "Unsupported display locale.")


def locale(request, params):
    defaults = {"language": "en-US", "region": "IN"}
    if request.user.is_authenticated:
        from accounts.models import UserPreferences

        pref = UserPreferences.objects.filter(user=request.user).first()
        if pref:
            defaults.update(language=pref.display_language, region=pref.region)
    values = {key: params.get(key, default) for key, default in defaults.items()}
    validate_locale(**values)
    return values


def metadata(request, params, data):
    locale(request, params)
    return metadata_values()


def validate_filters(filters):
    if "q" in filters and len(filters["q"].strip()) < 2:
        raise APIError("validation_error", "Search text must contain at least two characters.")
    if set(filters.get("genres", [])) - set(GENRE_KEYS):
        raise APIError("validation_error", "Unsupported genre.")
    for lower, upper in (("year_from", "year_to"), ("runtime_min", "runtime_max")):
        if lower in filters and upper in filters and filters[lower] > filters[upper]:
            raise APIError(
                "validation_error",
                "Invalid filter range.",
                fields={upper: [f"Must be at least {lower}."]},
            )
    if filters.get("original_language") and filters["original_language"] not in {
        language["code"] for language in metadata_values()["languages"]
    }:
        raise APIError("validation_error", "Unsupported original language.")
    if bool(filters.get("person_id")) != bool(filters.get("person_role")):
        raise APIError("validation_error", "person_id and person_role must be supplied together.")
    if (filters.get("q") and filters.get("person_id")) or (
        (filters.get("q") or filters.get("person_id"))
        and filters.get("feed", "discover") != "discover"
    ):
        raise APIError("validation_error", "Conflicting search/feed filters.")


def matches(title, filters):
    keys = {g["key"] for g in title["genres"]}
    if not set(filters.get("genres", [])).issubset(keys):
        return False
    for low, high, field in (
        ("year_from", "year_to", "year"),
        ("runtime_min", "runtime_max", "runtime_minutes"),
    ):
        value = title[field]
        if low in filters and (value is None or value < filters[low]):
            return False
        if high in filters and (value is None or value > filters[high]):
            return False
    if "min_rating" in filters and (
        title["rating"] is None or title["rating"] < filters["min_rating"]
    ):
        return False
    if (
        filters.get("original_language")
        and filters["original_language"] != title["original_language"]
    ):
        return False
    if filters.get("feed") == "top_rated" and title["vote_count"] < 200:
        return False
    if filters.get("feed") == "new_releases":
        if not title["release_date"] or not (
            str(date.today() - timedelta(days=90)) <= title["release_date"] <= str(date.today())
        ):
            return False
    return True


def raw_detail(media, tmdb_id, language="en-US", append=False):
    params = {"language": language}
    if append:
        params["append_to_response"] = "credits,videos"
        params["include_video_language"] = language.split("-")[0] + ",en"
    result = TMDBClient().get(f"{media}/{tmdb_id}", params, ttl=21600, missing_ok=True)
    if not isinstance(result, dict) or result.get("adult"):
        raise APIError("not_found", "Title not found.", 404)
    summary(result, media)  # Validate core identity/name before trusting its payload.
    return result


def candidates(filters, language="en-US", region="IN", seed_genres=None):
    validate_filters(filters)
    media_types = (
        ["movie", "tv"] if filters.get("media_type", "all") == "all" else [filters["media_type"]]
    )
    runtime_filter = "runtime_min" in filters or "runtime_max" in filters
    client = TMDBClient()
    raw_groups = {}
    for media in media_types:
        selected = filters.get("genres", [])
        inverse = {key: gid for gid, keys in GENRES[media].items() for key in keys}
        if any(key not in inverse for key in selected):
            raw_groups[media] = []
            continue
        query = {"language": language, "include_adult": "false"}
        if filters.get("person_id"):
            all_credits = client.get(
                f"person/{filters['person_id']}/combined_credits", {"language": language}
            )
            entries = all_credits.get("cast" if filters["person_role"] == "actor" else "crew", [])
            entries = [
                r
                for r in entries
                if r.get("media_type") == media
                and (filters["person_role"] == "actor" or r.get("job") == "Director")
            ]
            entries.sort(key=lambda r: (-(r.get("popularity") or 0), r.get("id", 0)))
            raw_groups[media] = entries[: 20 if len(media_types) == 2 else 40]
            continue
        feed = filters.get("feed", "discover")
        if filters.get("q"):
            path = f"search/{media}"
            query["query"] = filters["q"].strip()
        elif feed == "trending":
            path = f"trending/{media}/week"
        else:
            path = f"discover/{media}"
            if selected:
                query["with_genres"] = ",".join(map(str, sorted({inverse[k] for k in selected})))
            elif seed_genres:
                mapped = sorted({inverse[k] for k in seed_genres if k in inverse})
                if mapped:
                    query["with_genres"] = "|".join(map(str, mapped))
            year_key = "primary_release_date" if media == "movie" else "first_air_date"
            if "year_from" in filters:
                query[year_key + ".gte"] = f"{filters['year_from']}-01-01"
            if "year_to" in filters:
                query[year_key + ".lte"] = f"{filters['year_to']}-12-31"
            for source, destination in (
                ("min_rating", "vote_average.gte"),
                ("original_language", "with_original_language"),
                ("runtime_min", "with_runtime.gte"),
                ("runtime_max", "with_runtime.lte"),
            ):
                if source in filters:
                    query[destination] = filters[source]
            query["sort_by"] = {
                "rating_desc": "vote_average.desc",
                "release_date_desc": year_key + ".desc",
                "release_date_asc": year_key + ".asc",
            }.get(filters.get("sort"), "popularity.desc")
            if feed == "top_rated":
                query.update({"vote_count.gte": 200, "sort_by": "vote_average.desc"})
            if feed == "new_releases":
                query.update(
                    {
                        year_key + ".gte": str(date.today() - timedelta(days=90)),
                        year_key + ".lte": str(date.today()),
                    }
                )
        entries = []
        for page in range(1, 2 if len(media_types) == 2 else 3):
            result = client.get(path, {**query, "page": page})
            if not isinstance(result, dict) or not isinstance(result.get("results"), list):
                raise APIError("upstream_invalid", "Invalid catalogue response.", 502)
            entries += result["results"][:20]
            if page >= result.get("total_pages", 1):
                break
        raw_groups[media] = entries[: 20 if len(media_types) == 2 else 40]
    output, seen = [], set()
    # Interleave upstream ranks with movie winning ties.
    for index in range(40):
        for media in media_types:
            entries = raw_groups.get(media, [])
            if runtime_filter:
                entries = entries[: 3 if len(media_types) == 2 else 6]
            if index >= len(entries):
                continue
            raw = entries[index]
            key = (media, raw.get("id"))
            if key in seen or raw.get("adult"):
                continue
            seen.add(key)
            title = summary(
                raw_detail(media, raw["id"], language) if runtime_filter else raw, media
            )
            if matches(title, filters):
                output.append(title)
    sort = filters.get("sort", "relevance")
    if filters.get("feed") == "top_rated" and sort == "relevance":
        sort = "rating_desc"
    if sort != "relevance":
        output.sort(key=lambda t: (t["media_type"], t["tmdb_id"]))
        field = {
            "popularity_desc": "popularity",
            "rating_desc": "rating",
            "release_date_desc": "release_date",
            "release_date_asc": "release_date",
            "title_asc": "title",
        }[sort]
        output.sort(
            key=lambda t: (
                t[field]
                if t[field] is not None
                else (0 if field in ("popularity", "rating") else "")
            ),
            reverse=sort.endswith("desc"),
        )
        output.sort(key=lambda t: t[field] is None)
    return output


def discover(request, params, data):
    values = locale(request, params)
    validate_filters(params)
    query = {**params, **values}
    limit = 6 if "runtime_min" in params or "runtime_max" in params else 40
    if params.get("media_type", "all") == "all":
        selected = set(params.get("genres", []))
        branches = sum(
            selected.issubset({k for v in GENRES[m].values() for k in v}) for m in ("movie", "tv")
        )
        limit = max(1, limit * branches // 2)
    return snapshot_page(
        request, query, lambda: candidates(params, **values), "public", "bounded_candidates", limit
    )


def search_people(request, params, data):
    if len(params["q"].strip()) < 2:
        raise APIError("validation_error", "Search text must contain at least two characters.")
    values = locale(request, params)

    def fetch():
        rows = []
        for page in (1, 2):
            response = TMDBClient().get(
                "search/person",
                {
                    "query": params["q"].strip(),
                    "language": values["language"],
                    "include_adult": "false",
                    "page": page,
                },
            )
            if not isinstance(response, dict) or not isinstance(response.get("results"), list):
                raise APIError("upstream_invalid", "Invalid people response.", 502)
            rows += [person(row) for row in response["results"][:20] if not row.get("adult")]
            if page >= response.get("total_pages", 1):
                break
        return list({r["tmdb_id"]: r for r in rows}.values())

    return snapshot_page(request, {**params, **values}, fetch, "public", "bounded_candidates", 40)


def details(request, params, data):
    values = locale(request, params)
    media, tmdb_id = params["media_type"], params["tmdb_id"]
    raw = raw_detail(media, tmdb_id, values["language"], append=True)
    warnings = []
    credits = raw.get("credits")
    if not isinstance(credits, dict):
        credits = {}
        warnings.append(
            {"code": "credits_unavailable", "message": "Credits temporarily unavailable."}
        )
    video_section = raw.get("videos")
    videos = video_section.get("results") if isinstance(video_section, dict) else None
    if not isinstance(videos, list):
        videos = []
        warnings.append(
            {"code": "trailers_unavailable", "message": "Trailers temporarily unavailable."}
        )
    try:
        selected = trailers(videos, values["language"])
    except APIError:
        selected = []
        warnings.append(
            {"code": "trailers_unavailable", "message": "Trailers temporarily unavailable."}
        )
    availability = {
        "region": values["region"],
        "status": "not_available",
        "link": None,
        **{kind: [] for kind in ("flatrate", "free", "ads", "rent", "buy")},
        "attribution": "JustWatch",
    }
    try:
        provider_response = TMDBClient().get(f"{media}/{tmdb_id}/watch/providers", ttl=3600)
        region = provider_response.get("results", {}).get(values["region"], {})
        availability["link"] = region.get("link")
        for kind in ("flatrate", "free", "ads", "rent", "buy"):
            availability[kind] = [
                {
                    "id": p["provider_id"],
                    "name": p["provider_name"],
                    "logo_url": image(p.get("logo_path")),
                }
                for p in region.get(kind, [])
            ]
        if any(availability[k] for k in ("flatrate", "free", "ads", "rent", "buy")):
            availability["status"] = "available"
    except (APIError, KeyError, TypeError, AttributeError):
        availability["status"] = "unavailable"
        availability.update({kind: [] for kind in ("flatrate", "free", "ads", "rent", "buy")})
        availability["link"] = None
        warnings.append(
            {
                "code": "availability_unavailable",
                "message": "Streaming availability temporarily unavailable.",
            }
        )
    normalized_title = summary(raw, media)
    # Refresh only already-referenced summaries, never copy discovery catalogue rows.
    from django.utils import timezone

    from catalog.models import TitleSnapshot

    TitleSnapshot.objects.filter(media_type=media, tmdb_id=tmdb_id).update(
        summary=normalized_title,
        genre_keys=[g["key"] for g in normalized_title["genres"]],
        fetched_at=timezone.now(),
        metadata_status="available",
    )
    return {
        "title": normalized_title,
        "tagline": raw.get("tagline") or "",
        "status": raw.get("status") or "",
        "number_of_seasons": raw.get("number_of_seasons") if media == "tv" else None,
        "number_of_episodes": raw.get("number_of_episodes") if media == "tv" else None,
        "cast": [
            {"person": person(p), "role": "actor", "character": p.get("character")}
            for p in credits.get("cast", [])[:20]
        ],
        "directors": [
            {"person": person(p), "role": "director", "character": None}
            for p in credits.get("crew", [])
            if p.get("job") == "Director"
        ],
        "creators": [
            {"person": person(p), "role": "creator", "character": None}
            for p in raw.get("created_by", [])
        ],
        "trailers": selected,
        "selected_trailer_id": selected[0]["id"] if selected else None,
        "availability": availability,
        "warnings": warnings,
    }
