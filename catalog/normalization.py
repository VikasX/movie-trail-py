# FILE PURPOSE: Translates TMDB movie/TV differences into the JSON shapes our React UI expects.
# Import math so the code below can use that module namespace.
import math

# Import re so the code below can use that module namespace.
import re

# Import date from datetime (the named Python helper module).
from datetime import date as calendar_date

# Import wraps from functools (the named Python helper module).
from functools import wraps

# Import median from statistics (the named Python helper module).
from statistics import median

# Import APIError from common.errors (our shared API layer).
from common.errors import APIError

# Canonical keys intentionally expand TMDB's combined TV categories.
# Set GENRES: build a dictionary with named fields such as movie, tv.
GENRES = {
    "movie": {
        28: ["action"],
        12: ["adventure"],
        16: ["animation"],
        35: ["comedy"],
        80: ["crime"],
        99: ["documentary"],
        18: ["drama"],
        10751: ["family"],
        14: ["fantasy"],
        36: ["history"],
        27: ["horror"],
        10402: ["music"],
        9648: ["mystery"],
        10749: ["romance"],
        878: ["sci-fi"],
        53: ["thriller"],
        10752: ["war"],
        37: ["western"],
    },
    "tv": {
        10759: ["action", "adventure"],
        16: ["animation"],
        35: ["comedy"],
        80: ["crime"],
        99: ["documentary"],
        18: ["drama"],
        10751: ["family"],
        10762: ["kids"],
        9648: ["mystery"],
        10763: ["news"],
        10764: ["reality"],
        10765: ["sci-fi", "fantasy"],
        10766: ["soap"],
        10767: ["talk"],
        10768: ["war-politics"],
        37: ["western"],
    },
}
# Set GENRE_KEYS: return a separately sorted sequence, leaving the original collection unchanged.
GENRE_KEYS = sorted(
    {key for mapping in GENRES.values() for keys in mapping.values() for key in keys}
)
# Set MOODS: build an ordered list of 5 entries.
MOODS = [
    {
        "key": "feel_good",
        "label": "Feel-Good",
        "genre_keys": ["comedy", "animation", "family"],
        "keyword_ids": [],
    },
    {
        "key": "mind_bending",
        "label": "Mind-Bending",
        "genre_keys": ["sci-fi", "mystery", "fantasy"],
        "keyword_ids": [],
    },
    {
        "key": "dark",
        "label": "Dark",
        "genre_keys": ["thriller", "horror", "crime"],
        "keyword_ids": [],
    },
    {
        "key": "relaxing",
        "label": "Relaxing",
        "genre_keys": ["comedy", "family", "documentary"],
        "keyword_ids": [],
    },
    {
        "key": "family_night",
        "label": "Family Night",
        "genre_keys": ["animation", "family"],
        "keyword_ids": [],
    },
]


# Wrap a translator so broken external data becomes a safe 502 instead of a Python traceback.
def validated_upstream(function):
    # Run the wrapped translator and turn common malformed-data errors into a predictable API
    # failure.
    @wraps(function)
    # INPUTS TO THIS FUNCTION: function = argument supplied by the caller.
    def wrapped(*args, **kwargs):
        # Attempt this block; the following except branches handle expected failures without
        # continuing the success path.
        try:
            # Return the result to the caller: call function with the inputs shown; its definition
            # explains the checks, side effects and return value.
            return function(*args, **kwargs)
        # Handle (KeyError, TypeError, ValueError, AttributeError) here. The original exception is
        # not automatically safe to expose to the client.
        except (KeyError, TypeError, ValueError, AttributeError):
            # Stop this action with safe API error 'upstream_invalid' (HTTP 502). The common
            # handler builds its JSON envelope.
            raise APIError("upstream_invalid", "Invalid metadata response.", 502) from None

    # Return the result to the caller: reuse wrapped, which was prepared earlier in this function.
    return wrapped


# Build an allowed TMDB image-CDN URL from a safe image path; return None when no valid image
# exists.
def image(path, size="w500"):
    # INPUTS TO THIS FUNCTION: path = argument supplied by the caller; size = argument supplied by
    # the caller.
    # Enter this branch only when not isinstance(path, str) or not
    # re.fullmatch('/[A-Za-z0-9_.-]+', path). Otherwise execution uses its alternative or
    # continues below.
    if not isinstance(path, str) or not re.fullmatch(r"/[A-Za-z0-9_.-]+", path):
        # Return the result to the caller: use None to represent no known value (JSON null at the
        # API boundary).
        return None
    # Return the result to the caller: evaluate f'https://image.tmdb.org/t/p/{size}{path}'.
    return f"https://image.tmdb.org/t/p/{size}{path}"


# Translate media-specific TMDB genre numbers into stable names such as animation or sci-fi.
def genre_keys(data, media):
    # INPUTS TO THIS FUNCTION: data = validated JSON; media = argument supplied by the caller.
    # Set ids: look up a named setting/value or make the indicated GET call; the surrounding
    # object determines which.
    ids = data.get(
        "genre_ids", [g.get("id") for g in data.get("genres", []) if isinstance(g, dict)]
    )
    # Return the result to the caller: return a separately sorted sequence, leaving the original
    # collection unchanged.
    return sorted({k for gid in ids for k in GENRES[media].get(gid, [])})


# Build one consistent title card from either a TMDB movie object or a TV object.
@validated_upstream
def summary(data, media):
    # INPUTS TO THIS FUNCTION: data = validated JSON; media = argument supplied by the caller.
    # Enter this branch only when not isinstance(data, dict) or not isinstance(data.get('id'),
    # int) or data['id'] <= 0. Otherwise execution uses its alternative or continues below.
    if not isinstance(data, dict) or not isinstance(data.get("id"), int) or data["id"] <= 0:
        # Stop this action with safe API error 'upstream_invalid' (HTTP 502). The common handler
        # builds its JSON envelope.
        raise APIError("upstream_invalid", "Invalid title metadata.", 502)
    # name holds a display name or field label; collection names are trimmed and checked for
    # allowed length. Next, choose data.get('title') when media == 'movie'; otherwise use
    # data.get('name').
    name = data.get("title") if media == "movie" else data.get("name")
    # Enter this branch only when not isinstance(name, str) or not name. Otherwise execution uses
    # its alternative or continues below.
    if not isinstance(name, str) or not name:
        # Stop this action with safe API error 'upstream_invalid' (HTTP 502). The common handler
        # builds its JSON envelope.
        raise APIError("upstream_invalid", "Invalid title metadata.", 502)
    # Set date: evaluate data.get('release_date' if media == 'movie' else 'first_air_date') or
    # None.
    date = data.get("release_date" if media == "movie" else "first_air_date") or None
    # Enter this branch only when date and (not re.fullmatch('\\d{4}-\\d{2}-\\d{2}', date)).
    # Otherwise execution uses its alternative or continues below.
    if date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        # Set date: use None to represent no known value (JSON null at the API boundary).
        date = None
    # Enter this branch only when date. Otherwise execution uses its alternative or continues
    # below.
    if date:
        # Call calendar_date.fromisoformat with the inputs shown; its definition explains the
        # checks, side effects and return value.
        calendar_date.fromisoformat(date)
    # Repeat the following block for each field from ('vote_average', 'vote_count', 'popularity').
    # Each iteration handles that one item/pair.
    for field in ("vote_average", "vote_count", "popularity"):
        # value holds a value being compared to a filter, or the collection summary returned next
        # to its items. Next, look up a named setting/value or make the indicated GET call; the
        # surrounding object determines which.
        value = data.get(field)
        # Enter this branch only when value is not None and (isinstance(value, bool) or not
        # isinstance(value, (int, float)) or (not math.isfinite(value))). Otherwise execution uses
        # its alternative or continues below.
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            # Raise ValueError; normal execution of this block stops here.
            raise ValueError
    # Enter this branch only when data.get('vote_average') is not None and (not 0 <=
    # data['vote_average'] <= 10). Otherwise execution uses its alternative or continues below.
    if data.get("vote_average") is not None and not 0 <= data["vote_average"] <= 10:
        # Raise ValueError; normal execution of this block stops here.
        raise ValueError
    # Set runtime: choose data.get('runtime') when media == 'movie'; otherwise use None.
    runtime = data.get("runtime") if media == "movie" else None
    # Enter this branch only when media == 'tv'. Otherwise execution uses its alternative or
    # continues below.
    if media == "tv":
        # known holds a set of documented query names, used to detect typos or unsupported
        # options. Next, build a list for each n in data.get('episode_run_time', []); keep only
        # entries passing isinstance(n, int) and n > 0.
        known = [n for n in data.get("episode_run_time", []) if isinstance(n, int) and n > 0]
        # Set runtime: choose int(median(known) + 0.5) when known; otherwise use None.
        runtime = int(median(known) + 0.5) if known else None
    # Enter this branch only when not isinstance(runtime, int) or runtime <= 0. Otherwise
    # execution uses its alternative or continues below.
    if not isinstance(runtime, int) or runtime <= 0:
        # Set runtime: use None to represent no known value (JSON null at the API boundary).
        runtime = None
    # Return this named-field dictionary; API handlers turn it into JSON, while helper callers use
    # it directly.
    return {
        # Separates movies from TV. Always combine this with tmdb_id for title identity.
        "media_type": media,
        # The identifier assigned by TMDB, not our PostgreSQL row primary key.
        "tmdb_id": data["id"],
        # The normalized card or title reference used here; the surrounding schema distinguishes a
        # string title from a nested card.
        "title": name,
        # TMDB original-language name, kept separately from the display title.
        "original_title": data.get("original_title" if media == "movie" else "original_name")
        or name,
        # The synopsis text; missing text is represented by an empty string.
        "overview": data.get("overview") or "",
        # Movie primary release date or TV first-air date; unknown values are null.
        "release_date": date,
        # Year derived from that movie release/TV first-air date, not the current calendar year.
        "year": int(date[:4]) if date else None,
        # A validated TMDB image-CDN URL, or null when no poster is known.
        "poster_url": image(data.get("poster_path")),
        # A wider TMDB background-image URL, independent of the poster.
        "backdrop_url": image(data.get("backdrop_path"), "w1280"),
        "genres": [
            {"key": key, "name": key.replace("-", " ").title()} for key in genre_keys(data, media)
        ],
        # The title original language, separate from the language chosen for displayed metadata.
        "original_language": data.get("original_language") or "",
        # TMDB rating on its 0–10 scale. This is not a CineScope user personal rating.
        "rating": data.get("vote_average") if data.get("vote_count", 0) else None,
        # The upstream number of TMDB votes; it helps distinguish unrated titles from a known
        # score.
        "vote_count": max(0, data.get("vote_count") or 0),
        # TMDB popularity used for ordering/relative scoring, not a probability or user rating.
        "popularity": max(0, data.get("popularity") or 0),
        # Known movie duration or normalized TV episode duration. Unknown is null, not zero.
        "runtime_minutes": runtime,
        # Says whether the runtime refers to a movie, episode or an unknown value.
        "runtime_basis": ("movie" if media == "movie" else "episode") if runtime else "unknown",
        # Indicates whether the stored metadata is available, stale or unavailable.
        "metadata_status": "available",
    }


# Reduce a TMDB person object to the public fields needed by cast/search results.
@validated_upstream
def person(data):
    # INPUTS TO THIS FUNCTION: data = validated JSON.
    # Enter this branch only when not isinstance(data.get('id'), int) or data['id'] <= 0.
    # Otherwise execution uses its alternative or continues below.
    if not isinstance(data.get("id"), int) or data["id"] <= 0:
        # Raise ValueError; normal execution of this block stops here.
        raise ValueError
    # Return this named-field dictionary; API handlers turn it into JSON, while helper callers use
    # it directly.
    return {
        # The identifier assigned by TMDB, not our PostgreSQL row primary key.
        "tmdb_id": data["id"],
        "name": data.get("name") or "",
        "known_for_department": data.get("known_for_department") or "",
        "profile_url": image(data.get("profile_path")),
    }


# Keep allowed YouTube videos, sort by our preference rules and build safe playback URLs.
@validated_upstream
def trailers(videos, language):
    # INPUTS TO THIS FUNCTION: videos = argument supplied by the caller; language = argument
    # supplied by the caller.
    # Set preferred: read the entry indexed by 0 from language.split('-').
    preferred = language.split("-")[0]
    # Set eligible: build a list for each v in videos; keep only entries passing v.get('site') ==
    # 'YouTube' and v.get('type') in ('Trailer', 'Teaser', 'Clip') and
    # re.fullmatch('[A-Za-z0-9_-]{11}', str(v.get('key', ''))) and (v.get('iso_639_1') in
    # {preferred, 'en'}).
    eligible = [
        v
        for v in videos
        if v.get("site") == "YouTube"
        and v.get("type") in ("Trailer", "Teaser", "Clip")
        and re.fullmatch(r"[A-Za-z0-9_-]{11}", str(v.get("key", "")))
        and v.get("iso_639_1") in {preferred, "en"}
    ]
    # Stable sort: newest first within language/kind/official priority.
    # Reorder the existing list using this key; reverse=true means descending.
    eligible.sort(key=lambda v: str(v.get("id", "")))
    # Reorder the existing list using this key; reverse=true means descending.
    eligible.sort(key=lambda v: v.get("published_at") or "", reverse=True)
    # Reorder the existing list using this key; reverse=true means descending.
    eligible.sort(
        key=lambda v: (
            0 if v.get("iso_639_1") == preferred else 1,
            {"Trailer": 0, "Teaser": 1, "Clip": 2}[v["type"]],
            not bool(v.get("official")),
        )
    )
    # Return the result to the caller: build a list for each v in eligible[:20].
    return [
        {
            "id": str(v["id"]),
            "site": "YouTube",
            # Validated YouTube video identifier used to construct embed/watch URLs.
            "youtube_key": v["key"],
            "name": v.get("name") or "",
            "kind": v["type"],
            "official": bool(v.get("official")),
            "language": v.get("iso_639_1") or "en",
            "published_at": v.get("published_at") or None,
            # Browser playback address; the backend provides metadata rather than hosting the
            # video.
            "embed_url": f"https://www.youtube-nocookie.com/embed/{v['key']}",
            # Ordinary YouTube viewing link for the same video.
            "watch_url": f"https://www.youtube.com/watch?v={v['key']}",
        }
        for v in eligible[:20]
    ]
