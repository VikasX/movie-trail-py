import math
import re
from datetime import date as calendar_date
from functools import wraps
from statistics import median

from common.errors import APIError

# Canonical keys intentionally expand TMDB's combined TV categories.
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
GENRE_KEYS = sorted(
    {key for mapping in GENRES.values() for keys in mapping.values() for key in keys}
)
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


def validated_upstream(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (KeyError, TypeError, ValueError, AttributeError):
            raise APIError("upstream_invalid", "Invalid metadata response.", 502) from None

    return wrapped


def image(path, size="w500"):
    if not isinstance(path, str) or not re.fullmatch(r"/[A-Za-z0-9_.-]+", path):
        return None
    return f"https://image.tmdb.org/t/p/{size}{path}"


def genre_keys(data, media):
    ids = data.get(
        "genre_ids", [g.get("id") for g in data.get("genres", []) if isinstance(g, dict)]
    )
    return sorted({k for gid in ids for k in GENRES[media].get(gid, [])})


@validated_upstream
def summary(data, media):
    if not isinstance(data, dict) or not isinstance(data.get("id"), int) or data["id"] <= 0:
        raise APIError("upstream_invalid", "Invalid title metadata.", 502)
    name = data.get("title") if media == "movie" else data.get("name")
    if not isinstance(name, str) or not name:
        raise APIError("upstream_invalid", "Invalid title metadata.", 502)
    date = data.get("release_date" if media == "movie" else "first_air_date") or None
    if date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        date = None
    if date:
        calendar_date.fromisoformat(date)
    for field in ("vote_average", "vote_count", "popularity"):
        value = data.get(field)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError
    if data.get("vote_average") is not None and not 0 <= data["vote_average"] <= 10:
        raise ValueError
    runtime = data.get("runtime") if media == "movie" else None
    if media == "tv":
        known = [n for n in data.get("episode_run_time", []) if isinstance(n, int) and n > 0]
        runtime = int(median(known) + 0.5) if known else None
    if not isinstance(runtime, int) or runtime <= 0:
        runtime = None
    return {
        "media_type": media,
        "tmdb_id": data["id"],
        "title": name,
        "original_title": data.get("original_title" if media == "movie" else "original_name")
        or name,
        "overview": data.get("overview") or "",
        "release_date": date,
        "year": int(date[:4]) if date else None,
        "poster_url": image(data.get("poster_path")),
        "backdrop_url": image(data.get("backdrop_path"), "w1280"),
        "genres": [
            {"key": key, "name": key.replace("-", " ").title()} for key in genre_keys(data, media)
        ],
        "original_language": data.get("original_language") or "",
        "rating": data.get("vote_average") if data.get("vote_count", 0) else None,
        "vote_count": max(0, data.get("vote_count") or 0),
        "popularity": max(0, data.get("popularity") or 0),
        "runtime_minutes": runtime,
        "runtime_basis": ("movie" if media == "movie" else "episode") if runtime else "unknown",
        "metadata_status": "available",
    }


@validated_upstream
def person(data):
    if not isinstance(data.get("id"), int) or data["id"] <= 0:
        raise ValueError
    return {
        "tmdb_id": data["id"],
        "name": data.get("name") or "",
        "known_for_department": data.get("known_for_department") or "",
        "profile_url": image(data.get("profile_path")),
    }


@validated_upstream
def trailers(videos, language):
    preferred = language.split("-")[0]
    eligible = [
        v
        for v in videos
        if v.get("site") == "YouTube"
        and v.get("type") in ("Trailer", "Teaser", "Clip")
        and re.fullmatch(r"[A-Za-z0-9_-]{11}", str(v.get("key", "")))
        and v.get("iso_639_1") in {preferred, "en"}
    ]
    # Stable sort: newest first within language/kind/official priority.
    eligible.sort(key=lambda v: str(v.get("id", "")))
    eligible.sort(key=lambda v: v.get("published_at") or "", reverse=True)
    eligible.sort(
        key=lambda v: (
            0 if v.get("iso_639_1") == preferred else 1,
            {"Trailer": 0, "Teaser": 1, "Clip": 2}[v["type"]],
            not bool(v.get("official")),
        )
    )
    return [
        {
            "id": str(v["id"]),
            "site": "YouTube",
            "youtube_key": v["key"],
            "name": v.get("name") or "",
            "kind": v["type"],
            "official": bool(v.get("official")),
            "language": v.get("iso_639_1") or "en",
            "published_at": v.get("published_at") or None,
            "embed_url": f"https://www.youtube-nocookie.com/embed/{v['key']}",
            "watch_url": f"https://www.youtube.com/watch?v={v['key']}",
        }
        for v in eligible[:20]
    ]
