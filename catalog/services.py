# FILE PURPOSE: Catalogue workflows: metadata, discovery, people search and a title-detail
# response.
# LEARNING TIP: read the matching walkthrough in docs/BACKEND_GUIDE.md, then follow the block
# comments below.
# Import date, timedelta from datetime (the named Python helper module).
from datetime import date, timedelta

# Import cache from django.core.cache (Django framework/database/security helpers).
from django.core.cache import cache

# Import TMDBClient from catalog.client (our TMDB/normalization layer).
from catalog.client import TMDBClient

# Import GENRE_KEYS, GENRES, MOODS, image, person, summary, trailers from catalog.normalization
# (our TMDB/normalization layer).
from catalog.normalization import GENRE_KEYS, GENRES, MOODS, image, person, summary, trailers

# Import APIError from common.errors (our shared API layer).
from common.errors import APIError

# Import snapshot_page from common.pagination (our shared API layer).
from common.pagination import snapshot_page


# Reuse configuration from shared cache, or fetch languages/countries and combine them with our
# mappings.
def metadata_values():
    # hit holds a remembered shared-cache result; None means the lookup did not find a usable
    # entry. Next, read a shared cache entry, or None on a miss.
    hit = cache.get("metadata:v2")
    # Enter this branch only when hit. Otherwise execution uses its alternative or continues
    # below.
    if hit:
        # Return the result to the caller: reuse hit, which was prepared earlier in this function.
        return hit
    # client holds the reusable interface for requesting TMDB data. Next, call TMDBClient with the
    # inputs shown; its definition explains the checks, side effects and return value.
    client = TMDBClient()
    # languages holds language configuration returned by TMDB. Next, look up a named setting/value
    # or make the indicated GET call; the surrounding object determines which.
    languages = client.get("configuration/languages", ttl=86400)
    # regions holds country/region codes used to validate display locale or streaming availability
    # selection. Next, look up a named setting/value or make the indicated GET call; the
    # surrounding object determines which.
    regions = client.get("configuration/countries", ttl=86400)
    # Enter this branch only when not isinstance(languages, list) or not isinstance(regions,
    # list). Otherwise execution uses its alternative or continues below.
    if not isinstance(languages, list) or not isinstance(regions, list):
        # Stop this action with safe API error 'upstream_invalid' (HTTP 502). The common handler
        # builds its JSON envelope.
        raise APIError("upstream_invalid", "Invalid provider configuration.", 502)
    # Set result: build a dictionary with named fields such as genres, languages, regions, moods,
    # mood_mapping_version, attribution.
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
        # Required source credit, such as JustWatch for regional provider data.
        "attribution": {
            "tmdb_notice": (
                "This product uses the TMDB API but is not endorsed or certified by TMDB."
            ),
            "tmdb_url": "https://www.themoviedb.org",
            "watch_providers": "JustWatch",
        },
    }
    # Remember this value for the specified lifetime.
    cache.set("metadata:v2", result, 86400)
    # Return the result to the caller: reuse result, which was prepared earlier in this function.
    return result


# Reject an unsupported display language or watch-provider region before doing catalogue work.
def validate_locale(language, region):
    # INPUTS TO THIS FUNCTION: language = argument supplied by the caller; region = argument
    # supplied by the caller.
    # Import re so the code below can use that module namespace.
    import re

    # Set metadata: call metadata_values with the inputs shown; its definition explains the
    # checks, side effects and return value.
    metadata = metadata_values()
    # codes holds supported language codes collected into a set for fast membership checks. Next,
    # build a set of distinct values for each language in metadata['languages'].
    codes = {language["code"] for language in metadata["languages"]}
    # regions holds country/region codes used to validate display locale or streaming availability
    # selection. Next, build a set of distinct values for each r in metadata['regions'].
    regions = {r["code"] for r in metadata["regions"]}
    # Enter this branch only when not re.fullmatch('[a-z]{2}(?:-[A-Z]{2})?', language) or
    # language.split('-')[0] not in codes or region not in regions. Otherwise execution uses its
    # alternative or continues below.
    if (
        not re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", language)
        or language.split("-")[0] not in codes
        or region not in regions
    ):
        # Stop this action with safe API error 'validation_error' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError("validation_error", "Unsupported language or region.")
    # Enter this branch only when '-' in language and language.split('-')[1] not in regions.
    # Otherwise execution uses its alternative or continues below.
    if "-" in language and language.split("-")[1] not in regions:
        # Stop this action with safe API error 'validation_error' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError("validation_error", "Unsupported display locale.")


# Choose explicit request settings first, then account preferences, then the application
# defaults.
def locale(request, params):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values.
    # defaults holds fallback locale/region settings, replaced by account preferences or explicit
    # request values. Next, build a dictionary with named fields such as language, region.
    defaults = {"language": "en-US", "region": "IN"}
    # The request has a recognized logged-in user; guest requests take the other path.
    if request.user.is_authenticated:
        # Import UserPreferences from accounts.models (our account layer).
        from accounts.models import UserPreferences

        # pref holds the user preference record, or unsaved default preferences when no record
        # exists. Next, evaluate this lookup and return one row, or None when no row matches.
        pref = UserPreferences.objects.filter(user=request.user).first()
        # Enter this branch only when pref. Otherwise execution uses its alternative or continues
        # below.
        if pref:
            # Write these fields directly on the matching rows through the orm.
            defaults.update(language=pref.display_language, region=pref.region)
    # values holds the chosen locale/region or the converted input values passed to later
    # validation. Next, build a lookup dictionary for each (key, default) in defaults.items().
    values = {key: params.get(key, default) for key, default in defaults.items()}
    # Call validate_locale with the inputs shown; its definition explains the checks, side effects
    # and return value.
    validate_locale(**values)
    # Return the result to the caller: reuse values, which was prepared earlier in this function.
    return values


# Check the requested locale and return the filter/mood configuration used by the UI.
def metadata(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # Call locale with the inputs shown; its definition explains the checks, side effects and
    # return value.
    locale(request, params)
    # Return the result to the caller: call metadata_values with the inputs shown; its definition
    # explains the checks, side effects and return value.
    return metadata_values()


# Check cross-field rules, including year/runtime ranges, known genres and conflicting search
# modes.
def validate_filters(filters):
    # INPUTS TO THIS FUNCTION: filters = argument supplied by the caller.
    # Enter this branch only when 'q' in filters and len(filters['q'].strip()) < 2. Otherwise
    # execution uses its alternative or continues below.
    if "q" in filters and len(filters["q"].strip()) < 2:
        # Stop this action with safe API error 'validation_error' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError("validation_error", "Search text must contain at least two characters.")
    # Enter this branch only when set(filters.get('genres', [])) - set(GENRE_KEYS). Otherwise
    # execution uses its alternative or continues below.
    if set(filters.get("genres", [])) - set(GENRE_KEYS):
        # Stop this action with safe API error 'validation_error' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError("validation_error", "Unsupported genre.")
    # Repeat the following block for each (lower, upper) from (('year_from', 'year_to'),
    # ('runtime_min', 'runtime_max')). Each iteration handles that one item/pair.
    for lower, upper in (("year_from", "year_to"), ("runtime_min", "runtime_max")):
        # Enter this branch only when lower in filters and upper in filters and (filters[lower] >
        # filters[upper]). Otherwise execution uses its alternative or continues below.
        if lower in filters and upper in filters and filters[lower] > filters[upper]:
            # Stop this action with safe API error 'validation_error' (HTTP 400). The common
            # handler builds its JSON envelope.
            raise APIError(
                "validation_error",
                "Invalid filter range.",
                fields={upper: [f"Must be at least {lower}."]},
            )
    # Enter this branch only when filters.get('original_language') and
    # filters['original_language'] not in {language['code'] for language in
    # metadata_values()['languages']}. Otherwise execution uses its alternative or continues
    # below.
    if filters.get("original_language") and filters["original_language"] not in {
        language["code"] for language in metadata_values()["languages"]
    }:
        # Stop this action with safe API error 'validation_error' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError("validation_error", "Unsupported original language.")
    # Enter this branch only when bool(filters.get('person_id')) !=
    # bool(filters.get('person_role')). Otherwise execution uses its alternative or continues
    # below.
    if bool(filters.get("person_id")) != bool(filters.get("person_role")):
        # Stop this action with safe API error 'validation_error' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError("validation_error", "person_id and person_role must be supplied together.")
    # Enter this branch only when filters.get('q') and filters.get('person_id') or
    # ((filters.get('q') or filters.get('person_id')) and filters.get('feed', 'discover') !=
    # 'discover'). Otherwise execution uses its alternative or continues below.
    if (filters.get("q") and filters.get("person_id")) or (
        (filters.get("q") or filters.get("person_id"))
        and filters.get("feed", "discover") != "discover"
    ):
        # Stop this action with safe API error 'validation_error' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError("validation_error", "Conflicting search/feed filters.")


# Test one normalized card against every active filter; selected genres must all match.
def matches(title, filters):
    # INPUTS TO THIS FUNCTION: title = argument supplied by the caller; filters = argument
    # supplied by the caller.
    # Set keys: build a set of distinct values for each g in title['genres'].
    keys = {g["key"] for g in title["genres"]}
    # Enter this branch only when not set(filters.get('genres', [])).issubset(keys). Otherwise
    # execution uses its alternative or continues below.
    if not set(filters.get("genres", [])).issubset(keys):
        # Return False to report that this predicate/check did not pass.
        return False
    # Repeat the following block for each (low, high, field) from (('year_from', 'year_to',
    # 'year'), ('runtime_min', 'runtime_max', 'runtime_minutes')). Each iteration handles that one
    # item/pair.
    for low, high, field in (
        ("year_from", "year_to", "year"),
        ("runtime_min", "runtime_max", "runtime_minutes"),
    ):
        # value holds a value being compared to a filter, or the collection summary returned next
        # to its items. Next, read the entry indexed by field from title.
        value = title[field]
        # Enter this branch only when low in filters and (value is None or value < filters[low]).
        # Otherwise execution uses its alternative or continues below.
        if low in filters and (value is None or value < filters[low]):
            # Return False to report that this predicate/check did not pass.
            return False
        # Enter this branch only when high in filters and (value is None or value >
        # filters[high]). Otherwise execution uses its alternative or continues below.
        if high in filters and (value is None or value > filters[high]):
            # Return False to report that this predicate/check did not pass.
            return False
    # Enter this branch only when 'min_rating' in filters and (title['rating'] is None or
    # title['rating'] < filters['min_rating']). Otherwise execution uses its alternative or
    # continues below.
    if "min_rating" in filters and (
        title["rating"] is None or title["rating"] < filters["min_rating"]
    ):
        # Return False to report that this predicate/check did not pass.
        return False
    # Enter this branch only when filters.get('original_language') and
    # filters['original_language'] != title['original_language']. Otherwise execution uses its
    # alternative or continues below.
    if (
        filters.get("original_language")
        and filters["original_language"] != title["original_language"]
    ):
        # Return False to report that this predicate/check did not pass.
        return False
    # Enter this branch only when filters.get('feed') == 'top_rated' and title['vote_count'] <
    # 200. Otherwise execution uses its alternative or continues below.
    if filters.get("feed") == "top_rated" and title["vote_count"] < 200:
        # Return False to report that this predicate/check did not pass.
        return False
    # Enter this branch only when filters.get('feed') == 'new_releases'. Otherwise execution uses
    # its alternative or continues below.
    if filters.get("feed") == "new_releases":
        # Enter this branch only when not title['release_date'] or not str(date.today() -
        # timedelta(days=90)) <= title['release_date'] <= str(date.today()). Otherwise execution
        # uses its alternative or continues below.
        if not title["release_date"] or not (
            str(date.today() - timedelta(days=90)) <= title["release_date"] <= str(date.today())
        ):
            # Return False to report that this predicate/check did not pass.
            return False
    # Return True to report that this predicate/check passed.
    return True


# Read one TMDB movie/TV record and reject a missing, adult or malformed title.
def raw_detail(media, tmdb_id, language="en-US", append=False):
    # INPUTS TO THIS FUNCTION: media = argument supplied by the caller; tmdb_id = argument
    # supplied by the caller; language = argument supplied by the caller; append = argument
    # supplied by the caller.
    # params holds path/query settings; this name can also mean outbound TMDB parameters inside
    # catalogue helpers. Next, build a dictionary with named fields such as language.
    params = {"language": language}
    # Enter this branch only when append. Otherwise execution uses its alternative or continues
    # below.
    if append:
        # Set params['append_to_response']: use the fixed value 'credits,videos'.
        params["append_to_response"] = "credits,videos"
        # Set params['include_video_language']: calculate language.split('-')[0] + ',en' from the
        # intermediate values already prepared.
        params["include_video_language"] = language.split("-")[0] + ",en"
    # Set result: look up a named setting/value or make the indicated GET call; the surrounding
    # object determines which.
    result = TMDBClient().get(f"{media}/{tmdb_id}", params, ttl=21600, missing_ok=True)
    # Enter this branch only when not isinstance(result, dict) or result.get('adult'). Otherwise
    # execution uses its alternative or continues below.
    if not isinstance(result, dict) or result.get("adult"):
        # Stop this action with safe API error 'not_found' (HTTP 404). The common handler builds
        # its JSON envelope.
        raise APIError("not_found", "Title not found.", 404)
    # Call summary with the inputs shown; its definition explains the checks, side effects and
    # return value.
    summary(result, media)  # Validate core identity/name before trusting its payload.
    # Return the result to the caller: reuse result, which was prepared earlier in this function.
    return result


# Fetch a small source window, normalize/filter it and sort it; never crawl the entire
# catalogue.
def candidates(filters, language="en-US", region="IN", seed_genres=None):
    # INPUTS TO THIS FUNCTION: filters = argument supplied by the caller; language = argument
    # supplied by the caller; region = argument supplied by the caller; seed_genres = argument
    # supplied by the caller.
    # Call validate_filters with the inputs shown; its definition explains the checks, side
    # effects and return value.
    validate_filters(filters)
    # media_types holds the movie/TV branches this request will search; All creates both branches.
    # Next, choose ['movie', 'tv'] when filters.get('media_type', 'all') == 'all'; otherwise use
    # [filters['media_type']].
    media_types = (
        ["movie", "tv"] if filters.get("media_type", "all") == "all" else [filters["media_type"]]
    )
    # runtime_filter holds whether runtime is a hard constraint requiring the smaller hydration
    # window. Next, evaluate 'runtime_min' in filters or 'runtime_max' in filters.
    runtime_filter = "runtime_min" in filters or "runtime_max" in filters
    # client holds the reusable interface for requesting TMDB data. Next, call TMDBClient with the
    # inputs shown; its definition explains the checks, side effects and return value.
    client = TMDBClient()
    # raw_groups holds upstream candidate lists kept separate until movie/TV normalization is
    # complete. Next, build a dictionary with named fields.
    raw_groups = {}
    # Repeat the following block for each media from media_types. Each iteration handles that one
    # item/pair.
    for media in media_types:
        # selected holds the selected genres or selected video list, depending on the surrounding
        # function. Next, look up a named setting/value or make the indicated GET call; the
        # surrounding object determines which.
        selected = filters.get("genres", [])
        # Build canonical-name to TMDB-number lookup for this media branch.
        # inverse holds a canonical genre-name to TMDB-number lookup for the current media branch.
        # Next, build a lookup dictionary for each (gid, keys) in GENRES[media].items(); for each
        # key in keys.
        inverse = {key: gid for gid, keys in GENRES[media].items() for key in keys}
        # Do not weaken selected genres: an unmappable required genre excludes the whole branch.
        # Enter this branch only when any((key not in inverse for key in selected)). Otherwise
        # execution uses its alternative or continues below.
        if any(key not in inverse for key in selected):
            # Set raw_groups[media]: build an ordered list of 0 entries.
            raw_groups[media] = []
            # Skip the rest of this iteration and move to the next item or allowed retry.
            continue
        # query holds the outgoing parameter dictionary, built without changing the caller input
        # in place. Next, build a dictionary with named fields such as language, include_adult.
        query = {"language": language, "include_adult": "false"}
        # Enter this branch only when filters.get('person_id'). Otherwise execution uses its
        # alternative or continues below.
        if filters.get("person_id"):
            # all_credits holds the selected person movie and TV credits returned by TMDB. Next,
            # look up a named setting/value or make the indicated GET call; the surrounding object
            # determines which.
            all_credits = client.get(
                f"person/{filters['person_id']}/combined_credits", {"language": language}
            )
            # entries holds a bounded upstream list, before translation to the final CineScope
            # card shape. Next, look up a named setting/value or make the indicated GET call; the
            # surrounding object determines which.
            entries = all_credits.get("cast" if filters["person_role"] == "actor" else "crew", [])
            # entries holds a bounded upstream list, before translation to the final CineScope
            # card shape. Next, build a list for each r in entries; keep only entries passing
            # r.get('media_type') == media and (filters['person_role'] == 'actor' or r.get('job')
            # == 'Director').
            entries = [
                r
                for r in entries
                if r.get("media_type") == media
                and (filters["person_role"] == "actor" or r.get("job") == "Director")
            ]
            # Reorder the existing list using this key; reverse=true means descending.
            entries.sort(key=lambda r: (-(r.get("popularity") or 0), r.get("id", 0)))
            # Set raw_groups[media]: read the entry indexed by :20 if len(media_types) == 2 else
            # 40 from entries.
            raw_groups[media] = entries[: 20 if len(media_types) == 2 else 40]
            # Skip the rest of this iteration and move to the next item or allowed retry.
            continue
        # feed holds which discovery rail is requested: ordinary discovery, trending, new releases
        # or top rated. Next, look up a named setting/value or make the indicated GET call; the
        # surrounding object determines which.
        feed = filters.get("feed", "discover")
        # Enter this branch only when filters.get('q'). Otherwise execution uses its alternative
        # or continues below.
        if filters.get("q"):
            # path holds the route to request externally or the frontend completion path; read the
            # surrounding function for its role. Next, evaluate f'search/{media}'.
            path = f"search/{media}"
            # Set query['query']: call filters['q'].strip with the inputs shown; its definition
            # explains the checks, side effects and return value.
            query["query"] = filters["q"].strip()
        # Enter this branch only when feed == 'trending'. Otherwise execution uses its alternative
        # or continues below.
        elif feed == "trending":
            # path holds the route to request externally or the frontend completion path; read the
            # surrounding function for its role. Next, evaluate f'trending/{media}/week'.
            path = f"trending/{media}/week"
        else:
            # path holds the route to request externally or the frontend completion path; read the
            # surrounding function for its role. Next, evaluate f'discover/{media}'.
            path = f"discover/{media}"
            # Enter this branch only when selected. Otherwise execution uses its alternative or
            # continues below.
            if selected:
                # Comma joins enforce AND for selected genres; pipes below are only for
                # recommendation seed alternatives.
                # Set query['with_genres']: call ','.join with the inputs shown; its definition
                # explains the checks, side effects and return value.
                query["with_genres"] = ",".join(map(str, sorted({inverse[k] for k in selected})))
            # Enter this branch only when seed_genres. Otherwise execution uses its alternative or
            # continues below.
            elif seed_genres:
                # mapped holds deduplicated upstream genre numbers for the selected recommendation
                # seeds. Next, return a separately sorted sequence, leaving the original
                # collection unchanged.
                mapped = sorted({inverse[k] for k in seed_genres if k in inverse})
                # Enter this branch only when mapped. Otherwise execution uses its alternative or
                # continues below.
                if mapped:
                    # Set query['with_genres']: call '|'.join with the inputs shown; its
                    # definition explains the checks, side effects and return value.
                    query["with_genres"] = "|".join(map(str, mapped))
            # year_key holds the TMDB date-field name; movie release dates and TV first-air dates
            # use different names. Next, choose 'primary_release_date' when media == 'movie';
            # otherwise use 'first_air_date'.
            year_key = "primary_release_date" if media == "movie" else "first_air_date"
            # Enter this branch only when 'year_from' in filters. Otherwise execution uses its
            # alternative or continues below.
            if "year_from" in filters:
                # Set query[year_key + '.gte']: evaluate f"{filters['year_from']}-01-01".
                query[year_key + ".gte"] = f"{filters['year_from']}-01-01"
            # Enter this branch only when 'year_to' in filters. Otherwise execution uses its
            # alternative or continues below.
            if "year_to" in filters:
                # Set query[year_key + '.lte']: evaluate f"{filters['year_to']}-12-31".
                query[year_key + ".lte"] = f"{filters['year_to']}-12-31"
            # Repeat the following block for each (source, destination) from (('min_rating',
            # 'vote_average.gte'), ('original_language', 'with_original_language'),
            # ('runtime_min', 'with_runtime.gte'), ('runtime_max', 'with_runtime.lte')). Each
            # iteration handles that one item/pair.
            for source, destination in (
                ("min_rating", "vote_average.gte"),
                ("original_language", "with_original_language"),
                ("runtime_min", "with_runtime.gte"),
                ("runtime_max", "with_runtime.lte"),
            ):
                # Enter this branch only when source in filters. Otherwise execution uses its
                # alternative or continues below.
                if source in filters:
                    # Set query[destination]: read the entry indexed by source from filters.
                    query[destination] = filters[source]
            # Set query['sort_by']: look up a named setting/value or make the indicated GET call;
            # the surrounding object determines which.
            query["sort_by"] = {
                "rating_desc": "vote_average.desc",
                "release_date_desc": year_key + ".desc",
                "release_date_asc": year_key + ".asc",
            }.get(filters.get("sort"), "popularity.desc")
            # Enter this branch only when feed == 'top_rated'. Otherwise execution uses its
            # alternative or continues below.
            if feed == "top_rated":
                # Write these fields directly on the matching rows through the orm.
                query.update({"vote_count.gte": 200, "sort_by": "vote_average.desc"})
            # Enter this branch only when feed == 'new_releases'. Otherwise execution uses its
            # alternative or continues below.
            if feed == "new_releases":
                # Write these fields directly on the matching rows through the orm.
                query.update(
                    {
                        year_key + ".gte": str(date.today() - timedelta(days=90)),
                        year_key + ".lte": str(date.today()),
                    }
                )
        # entries holds a bounded upstream list, before translation to the final CineScope card
        # shape. Next, build an ordered list of 0 entries.
        entries = []
        # Repeat the following block for each page from range(1, 2 if len(media_types) == 2 else
        # 3). Each iteration handles that one item/pair.
        for page in range(1, 2 if len(media_types) == 2 else 3):
            # Set result: look up a named setting/value or make the indicated GET call; the
            # surrounding object determines which.
            result = client.get(path, {**query, "page": page})
            # Enter this branch only when not isinstance(result, dict) or not
            # isinstance(result.get('results'), list). Otherwise execution uses its alternative or
            # continues below.
            if not isinstance(result, dict) or not isinstance(result.get("results"), list):
                # Stop this action with safe API error 'upstream_invalid' (HTTP 502). The common
                # handler builds its JSON envelope.
                raise APIError("upstream_invalid", "Invalid catalogue response.", 502)
            # Add to entries using read the entry indexed by :20 from result['results'].
            entries += result["results"][:20]
            # Enter this branch only when page >= result.get('total_pages', 1). Otherwise
            # execution uses its alternative or continues below.
            if page >= result.get("total_pages", 1):
                # Leave this loop now; no further source pages/items are attempted by this loop.
                break
        # Set raw_groups[media]: read the entry indexed by :20 if len(media_types) == 2 else 40
        # from entries.
        raw_groups[media] = entries[: 20 if len(media_types) == 2 else 40]
    # Prepare normalized results and deduplicate using media type plus ID, not ID alone.
    # Set (output, seen): keep these related values together as a tuple: [], set().
    output, seen = [], set()
    # Interleave upstream ranks with movie winning ties.
    # Repeat the following block for each index from range(40). Each iteration handles that one
    # item/pair.
    for index in range(40):
        # Repeat the following block for each media from media_types. Each iteration handles that
        # one item/pair.
        for media in media_types:
            # entries holds a bounded upstream list, before translation to the final CineScope
            # card shape. Next, look up a named setting/value or make the indicated GET call; the
            # surrounding object determines which.
            entries = raw_groups.get(media, [])
            # Choose the smaller deterministic window before reading runtime details, keeping
            # fan-out bounded.
            # Runtime affects correctness, so use the bounded detail-hydration path instead of
            # guessing it from list data.
            if runtime_filter:
                # entries holds a bounded upstream list, before translation to the final CineScope
                # card shape. Next, read the entry indexed by :3 if len(media_types) == 2 else 6
                # from entries.
                entries = entries[: 3 if len(media_types) == 2 else 6]
            # Enter this branch only when index >= len(entries). Otherwise execution uses its
            # alternative or continues below.
            if index >= len(entries):
                # Skip the rest of this iteration and move to the next item or allowed retry.
                continue
            # raw holds the source value before this step converts or normalizes it. Next, read
            # the entry indexed by index from entries.
            raw = entries[index]
            # Set key: keep these related values together as a tuple: media, raw.get('id').
            key = (media, raw.get("id"))
            # Enter this branch only when key in seen or raw.get('adult'). Otherwise execution
            # uses its alternative or continues below.
            if key in seen or raw.get("adult"):
                # Skip the rest of this iteration and move to the next item or allowed retry.
                continue
            # Add one value to a set or an absent cache key; sets avoid duplicate values.
            seen.add(key)
            # title holds a referenced title record or normalized card; this is deliberately
            # separate from an owner SavedTitle row. Next, call summary with the inputs shown; its
            # definition explains the checks, side effects and return value.
            title = summary(
                raw_detail(media, raw["id"], language) if runtime_filter else raw, media
            )
            # A candidate is returned only after all active predicates pass.
            # Enter this branch only when matches(title, filters). Otherwise execution uses its
            # alternative or continues below.
            if matches(title, filters):
                # Add one item at the end of this list.
                output.append(title)
    # sort holds the requested ordering rule for this bounded selection. Next, look up a named
    # setting/value or make the indicated GET call; the surrounding object determines which.
    sort = filters.get("sort", "relevance")
    # Enter this branch only when filters.get('feed') == 'top_rated' and sort == 'relevance'.
    # Otherwise execution uses its alternative or continues below.
    if filters.get("feed") == "top_rated" and sort == "relevance":
        # sort holds the requested ordering rule for this bounded selection. Next, use the fixed
        # value 'rating_desc'.
        sort = "rating_desc"
    # Enter this branch only when sort != 'relevance'. Otherwise execution uses its alternative or
    # continues below.
    if sort != "relevance":
        # Reorder the existing list using this key; reverse=true means descending.
        output.sort(key=lambda t: (t["media_type"], t["tmdb_id"]))
        # field holds the normalized card property used as the sort value. Next, read the entry
        # indexed by sort from {'popularity_desc': 'popularity', 'rating_desc': 'rating',
        # 'release_date_desc': 'release_date', 'release_date_asc': 'release_date', 'title_asc':
        # 'title'}.
        field = {
            "popularity_desc": "popularity",
            "rating_desc": "rating",
            "release_date_desc": "release_date",
            "release_date_asc": "release_date",
            "title_asc": "title",
        }[sort]
        # Reorder the existing list using this key; reverse=true means descending.
        output.sort(
            key=lambda t: (
                t[field]
                if t[field] is not None
                else (0 if field in ("popularity", "rating") else "")
            ),
            reverse=sort.endswith("desc"),
        )
        # Reorder the existing list using this key; reverse=true means descending.
        output.sort(key=lambda t: t[field] is None)
    # Return the result to the caller: reuse output, which was prepared earlier in this function.
    return output


# Validate the discovery request and put its bounded matching cards into snapshot pagination.
def discover(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # values holds the chosen locale/region or the converted input values passed to later
    # validation. Next, call locale with the inputs shown; its definition explains the checks,
    # side effects and return value.
    values = locale(request, params)
    # Call validate_filters with the inputs shown; its definition explains the checks, side
    # effects and return value.
    validate_filters(params)
    # query holds the outgoing parameter dictionary, built without changing the caller input in
    # place. Next, build a dictionary with named fields.
    query = {**params, **values}
    # limit holds the cap chosen for this operation: request rate, page/candidate count, or
    # recommendations. Next, choose 6 when 'runtime_min' in params or 'runtime_max' in params;
    # otherwise use 40.
    limit = 6 if "runtime_min" in params or "runtime_max" in params else 40
    # Enter this branch only when params.get('media_type', 'all') == 'all'. Otherwise execution
    # uses its alternative or continues below.
    if params.get("media_type", "all") == "all":
        # selected holds the selected genres or selected video list, depending on the surrounding
        # function. Next, make a set so duplicate entries disappear and membership checks are
        # straightforward.
        selected = set(params.get("genres", []))
        # branches holds how many media branches can satisfy every selected genre. Next, add all
        # generated values, such as genre weights or supported media branches.
        branches = sum(
            selected.issubset({k for v in GENRES[m].values() for k in v}) for m in ("movie", "tv")
        )
        # limit holds the cap chosen for this operation: request rate, page/candidate count, or
        # recommendations. Next, choose the largest value, or apply the shown fallback/bound.
        limit = max(1, limit * branches // 2)
    # Return the result to the caller: call snapshot_page with the inputs shown; its definition
    # explains the checks, side effects and return value.
    return snapshot_page(
        request, query, lambda: candidates(params, **values), "public", "bounded_candidates", limit
    )


# Find people by name so the UI can select a precise actor/director ID rather than guessing a
# name.
def search_people(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # Enter this branch only when len(params['q'].strip()) < 2. Otherwise execution uses its
    # alternative or continues below.
    if len(params["q"].strip()) < 2:
        # Stop this action with safe API error 'validation_error' (HTTP 400). The common handler
        # builds its JSON envelope.
        raise APIError("validation_error", "Search text must contain at least two characters.")
    # values holds the chosen locale/region or the converted input values passed to later
    # validation. Next, call locale with the inputs shown; its definition explains the checks,
    # side effects and return value.
    values = locale(request, params)

    def fetch():
        # Set rows: build an ordered list of 0 entries.
        rows = []
        # Repeat the following block for each page from (1, 2). Each iteration handles that one
        # item/pair.
        for page in (1, 2):
            # response holds the response produced by the next handler or external HTTP request.
            # Next, look up a named setting/value or make the indicated GET call; the surrounding
            # object determines which.
            response = TMDBClient().get(
                "search/person",
                {
                    "query": params["q"].strip(),
                    "language": values["language"],
                    "include_adult": "false",
                    "page": page,
                },
            )
            # Enter this branch only when not isinstance(response, dict) or not
            # isinstance(response.get('results'), list). Otherwise execution uses its alternative
            # or continues below.
            if not isinstance(response, dict) or not isinstance(response.get("results"), list):
                # Stop this action with safe API error 'upstream_invalid' (HTTP 502). The common
                # handler builds its JSON envelope.
                raise APIError("upstream_invalid", "Invalid people response.", 502)
            # Add to rows using build a list for each row in response['results'][:20]; keep only
            # entries passing not row.get('adult').
            rows += [person(row) for row in response["results"][:20] if not row.get("adult")]
            # Enter this branch only when page >= response.get('total_pages', 1). Otherwise
            # execution uses its alternative or continues below.
            if page >= response.get("total_pages", 1):
                # Leave this loop now; no further source pages/items are attempted by this loop.
                break
        # Return the result to the caller: call list with the inputs shown; its definition
        # explains the checks, side effects and return value.
        return list({r["tmdb_id"]: r for r in rows}.values())

    # Return the result to the caller: call snapshot_page with the inputs shown; its definition
    # explains the checks, side effects and return value.
    return snapshot_page(request, {**params, **values}, fetch, "public", "bounded_candidates", 40)


# Combine core title data, credits, trailers and regional availability into the detail-page
# response.
def details(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # values holds the chosen locale/region or the converted input values passed to later
    # validation. Next, call locale with the inputs shown; its definition explains the checks,
    # side effects and return value.
    values = locale(request, params)
    # Set (media, tmdb_id): keep these related values together as a tuple: params['media_type'],
    # params['tmdb_id'].
    media, tmdb_id = params["media_type"], params["tmdb_id"]
    # raw holds the source value before this step converts or normalizes it. Next, call raw_detail
    # with the inputs shown; its definition explains the checks, side effects and return value.
    raw = raw_detail(media, tmdb_id, values["language"], append=True)
    # warnings holds safe section-level notices; optional missing data should not become a
    # fabricated successful section. Next, build an ordered list of 0 entries.
    warnings = []
    # credits holds the appended cast/crew section, or an empty fallback if that optional section
    # is unavailable. Next, look up a named setting/value or make the indicated GET call; the
    # surrounding object determines which.
    credits = raw.get("credits")
    # Enter this branch only when not isinstance(credits, dict). Otherwise execution uses its
    # alternative or continues below.
    if not isinstance(credits, dict):
        # credits holds the appended cast/crew section, or an empty fallback if that optional
        # section is unavailable. Next, build a dictionary with named fields.
        credits = {}
        # Add one item at the end of this list.
        warnings.append(
            {"code": "credits_unavailable", "message": "Credits temporarily unavailable."}
        )
    # video_section holds the upstream video wrapper; confirm it is a dictionary before reading
    # its results. Next, look up a named setting/value or make the indicated GET call; the
    # surrounding object determines which.
    video_section = raw.get("videos")
    # videos holds upstream video candidates, before YouTube/type/language selection. Next, choose
    # video_section.get('results') when isinstance(video_section, dict); otherwise use None.
    videos = video_section.get("results") if isinstance(video_section, dict) else None
    # Enter this branch only when not isinstance(videos, list). Otherwise execution uses its
    # alternative or continues below.
    if not isinstance(videos, list):
        # videos holds upstream video candidates, before YouTube/type/language selection. Next,
        # build an ordered list of 0 entries.
        videos = []
        # Add one item at the end of this list.
        warnings.append(
            {"code": "trailers_unavailable", "message": "Trailers temporarily unavailable."}
        )
    # Attempt this block; the following except branches handle expected failures without
    # continuing the success path.
    try:
        # selected holds the selected genres or selected video list, depending on the surrounding
        # function. Next, call trailers with the inputs shown; its definition explains the checks,
        # side effects and return value.
        selected = trailers(videos, values["language"])
    # Handle APIError here. The original exception is not automatically safe to expose to the
    # client.
    except APIError:
        # selected holds the selected genres or selected video list, depending on the surrounding
        # function. Next, build an ordered list of 0 entries.
        selected = []
        # Add one item at the end of this list.
        warnings.append(
            {"code": "trailers_unavailable", "message": "Trailers temporarily unavailable."}
        )
    # availability holds the region-specific provider response being assembled with explicit empty
    # defaults. Next, build a dictionary with named fields such as region, status, link,
    # attribution.
    availability = {
        "region": values["region"],
        "status": "not_available",
        "link": None,
        **{kind: [] for kind in ("flatrate", "free", "ads", "rent", "buy")},
        # Required source credit, such as JustWatch for regional provider data.
        "attribution": "JustWatch",
    }
    # Attempt this block; the following except branches handle expected failures without
    # continuing the success path.
    try:
        # provider_response holds the upstream watch-provider result grouped by country. Next,
        # look up a named setting/value or make the indicated GET call; the surrounding object
        # determines which.
        provider_response = TMDBClient().get(f"{media}/{tmdb_id}/watch/providers", ttl=3600)
        # region holds the chosen country code or its corresponding provider-data section. Next,
        # look up a named setting/value or make the indicated GET call; the surrounding object
        # determines which.
        region = provider_response.get("results", {}).get(values["region"], {})
        # Set availability['link']: look up a named setting/value or make the indicated GET call;
        # the surrounding object determines which.
        availability["link"] = region.get("link")
        # Repeat the following block for each kind from ('flatrate', 'free', 'ads', 'rent',
        # 'buy'). Each iteration handles that one item/pair.
        for kind in ("flatrate", "free", "ads", "rent", "buy"):
            # Set availability[kind]: build a list for each p in region.get(kind, []).
            availability[kind] = [
                {
                    "id": p["provider_id"],
                    "name": p["provider_name"],
                    "logo_url": image(p.get("logo_path")),
                }
                for p in region.get(kind, [])
            ]
        # Enter this branch only when any((availability[k] for k in ('flatrate', 'free', 'ads',
        # 'rent', 'buy'))). Otherwise execution uses its alternative or continues below.
        if any(availability[k] for k in ("flatrate", "free", "ads", "rent", "buy")):
            # Set availability['status']: use the fixed value 'available'.
            availability["status"] = "available"
    # Handle (APIError, KeyError, TypeError, AttributeError) here. The original exception is not
    # automatically safe to expose to the client.
    except (APIError, KeyError, TypeError, AttributeError):
        # Set availability['status']: use the fixed value 'unavailable'.
        availability["status"] = "unavailable"
        # Write these fields directly on the matching rows through the orm.
        availability.update({kind: [] for kind in ("flatrate", "free", "ads", "rent", "buy")})
        # Set availability['link']: use None to represent no known value (JSON null at the API
        # boundary).
        availability["link"] = None
        # Add one item at the end of this list.
        warnings.append(
            {
                "code": "availability_unavailable",
                "message": "Streaming availability temporarily unavailable.",
            }
        )
    # Refresh metadata only for already-referenced titles; discovery does not import the whole
    # catalogue.
    # normalized_title holds the finished movie/TV card stored or returned using CineScope field
    # names. Next, call summary with the inputs shown; its definition explains the checks, side
    # effects and return value.
    normalized_title = summary(raw, media)
    # Refresh only already-referenced summaries, never copy discovery catalogue rows.
    # Import timezone from django.utils (Django framework/database/security helpers).
    from django.utils import timezone

    # Import TitleSnapshot from catalog.models (our TMDB/normalization layer).
    from catalog.models import TitleSnapshot

    # Write these fields directly on the matching rows through the orm.
    TitleSnapshot.objects.filter(media_type=media, tmdb_id=tmdb_id).update(
        summary=normalized_title,
        genre_keys=[g["key"] for g in normalized_title["genres"]],
        fetched_at=timezone.now(),
        metadata_status="available",
    )
    # Return this named-field dictionary; API handlers turn it into JSON, while helper callers use
    # it directly.
    return {
        # The normalized card or title reference used here; the surrounding schema distinguishes a
        # string title from a nested card.
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
        # Supported video metadata and safe YouTube URLs; no video file is downloaded here.
        "trailers": selected,
        # Points to the preferred entry in trailers; null means no playable selection.
        "selected_trailer_id": selected[0]["id"] if selected else None,
        # Streaming-provider information for the requested region, which may be temporarily
        # unavailable.
        "availability": availability,
        # Optional-section failures that can be displayed without hiding valid core title details.
        "warnings": warnings,
    }
