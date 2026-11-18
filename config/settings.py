# FILE PURPOSE: Application settings: environment values, database, security, integrations and
# logging.
"""Environment-driven settings shared by local development and Vercel."""

# Import os so the code below can use that module namespace.
import os

# Import Path from pathlib (the named Python helper module).
from pathlib import Path
from urllib.parse import urlsplit

# Import environ so the code below can use that module namespace.
import environ

# Import ImproperlyConfigured from django.core.exceptions (Django framework/database/security
# helpers).
from django.core.exceptions import ImproperlyConfigured

# Use the repository root as the anchor for local config, packaged docs and build-time static
# output.
# Set BASE_DIR: read Path(__file__).resolve().parent.parent from the indicated object.
BASE_DIR = Path(__file__).resolve().parent.parent
# Environment values are strings initially; django-environ converts booleans, lists and database
# URLs.
# Set env: call environ.Env with the inputs shown; its definition explains the checks, side
# effects and return value.
env = environ.Env()
IS_VERCEL = bool(os.environ.get("VERCEL"))
# Deployment environment variables take precedence over the local file.
# Enter this branch only when not os.environ.get('VERCEL') and (BASE_DIR / '.env').is_file().
# Otherwise execution uses its alternative or continues below.
if not os.environ.get("VERCEL") and (BASE_DIR / ".env").is_file():
    # Call environ.env.read_env with the inputs shown; its definition explains the checks, side
    # effects and return value.
    environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

# Hosted deployments always use production security, even if a local .env was imported.
# Keep detailed debug pages for local work only; Vercel always gets production security.
# Set DEBUG: choose False when os.environ.get('VERCEL'); otherwise use env.bool('DEBUG',
# default=False).
DEBUG = False if os.environ.get("VERCEL") else env.bool("DEBUG", default=False)
# Set SECRET_KEY: call env with the inputs shown; its definition explains the checks, side effects
# and return value.
SECRET_KEY = env("SECRET_KEY")
# Enter this branch only when not SECRET_KEY or (not DEBUG and len(SECRET_KEY) < 50). Otherwise
# execution uses its alternative or continues below.
if not SECRET_KEY or (not DEBUG and len(SECRET_KEY) < 50):
    # Raise ImproperlyConfigured; normal execution of this block stops here.
    raise ImproperlyConfigured("Set a unique SECRET_KEY of at least 50 characters.")
# Only accept HTTP requests naming approved backend/public proxy hosts.
# Set ALLOWED_HOSTS: call env.list with the inputs shown; its definition explains the checks, side
# effects and return value.
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
# Enter this branch only when os.environ.get('VERCEL'). Otherwise execution uses its alternative
# or continues below.
if os.environ.get("VERCEL"):
    # Trust only this project's exact deployment, branch and production hostnames.
    # Repeat the following block for each variable from ('VERCEL_URL', 'VERCEL_BRANCH_URL',
    # 'VERCEL_PROJECT_PRODUCTION_URL'). Each iteration handles that one item/pair.
    for variable in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
        # Set hostname: call env with the inputs shown; its definition explains the checks, side
        # effects and return value.
        hostname = env(variable, default="")
        # Enter this branch only when hostname and hostname not in ALLOWED_HOSTS. Otherwise
        # execution uses its alternative or continues below.
        if hostname and hostname not in ALLOWED_HOSTS:
            # Add one item at the end of this list.
            ALLOWED_HOSTS.append(hostname)
# Enter this branch only when not DEBUG and (not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS). Otherwise
# execution uses its alternative or continues below.
if not DEBUG and (
    not ALLOWED_HOSTS or any("*" in host or host.startswith(".") for host in ALLOWED_HOSTS)
):
    # Raise ImproperlyConfigured; normal execution of this block stops here.
    raise ImproperlyConfigured("Set explicit ALLOWED_HOSTS for production.")

# Tell Django which built-in features, third-party integrations and our feature apps to load.
# Set INSTALLED_APPS: build an ordered list of 18 entries.
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "core.apps.CoreConfig",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "accounts",
    "catalog",
    "library",
]
# Request/response wrappers run in order on the way in and reverse order on the way out.
# Set MIDDLEWARE: build an ordered list of 10 entries.
MIDDLEWARE = [
    "common.middleware.RequestMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "common.middleware.AdminLoginThrottleMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
# Set ROOT_URLCONF: use the fixed value 'config.urls'.
ROOT_URLCONF = "config.urls"
# Set WSGI_APPLICATION: use the fixed value 'config.wsgi.application'.
WSGI_APPLICATION = "config.wsgi.application"
# Django templates are still needed for admin and framework pages, even though React renders the
# UI.
# Set TEMPLATES: build an ordered list of 1 entries.
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Parse DATABASE_URL into Django PostgreSQL settings; credentials stay in the environment.
# Set DATABASES: build a dictionary with named fields such as default.
DATABASES = {"default": env.db("DATABASE_URL")}
# Set database: read the entry indexed by 'default' from DATABASES.
database = DATABASES["default"]
# Enter this branch only when database['ENGINE'] != 'django.db.backends.postgresql'. Otherwise
# execution uses its alternative or continues below.
if database["ENGINE"] != "django.db.backends.postgresql":
    # Raise ImproperlyConfigured; normal execution of this block stops here.
    raise ImproperlyConfigured("DATABASE_URL must use PostgreSQL.")
# Set database['CONN_MAX_AGE']: use the fixed value 0.
database["CONN_MAX_AGE"] = 0
# Set options: reuse the existing entry, or create the provided starting value only if absent.
options = database.setdefault("OPTIONS", {})
# Require encrypted connections, preserving stronger certificate verification if supplied.
# Enter this branch only when options.get('sslmode', 'require') not in {'require', 'verify-ca',
# 'verify-full'}. Otherwise execution uses its alternative or continues below.
if options.get("sslmode", "require") not in {"require", "verify-ca", "verify-full"}:
    # Raise ImproperlyConfigured; normal execution of this block stops here.
    raise ImproperlyConfigured("DATABASE_URL must require PostgreSQL SSL.")
# Reuse the existing entry, or create the provided starting value only if absent.
options.setdefault("sslmode", "require")
# Reuse the existing entry, or create the provided starting value only if absent.
options.setdefault("connect_timeout", 5)

# Use Django password-strength checks in account creation and password reset.
# Set AUTH_PASSWORD_VALIDATORS: build an ordered list of 4 entries.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
# Set LANGUAGE_CODE: use the fixed value 'en-us'.
LANGUAGE_CODE = "en-us"
# Set TIME_ZONE: use the fixed value 'UTC'.
TIME_ZONE = "UTC"
# Set USE_I18N: use the boolean True.
USE_I18N = True
# Set USE_TZ: use the boolean True.
USE_TZ = True
# Set DEFAULT_AUTO_FIELD: use the fixed value 'django.db.models.BigAutoField'.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# Set STATIC_URL: use the fixed value '/static/'.
STATIC_URL = "/static/"
# Set STATIC_ROOT: calculate BASE_DIR / 'staticfiles' from the intermediate values already
# prepared.
STATIC_ROOT = BASE_DIR / "staticfiles"

# Project-wide DRF defaults; product views also apply operation-specific contract security.
# Set REST_FRAMEWORK: build a dictionary with named fields such as DEFAULT_RENDERER_CLASSES,
# DEFAULT_PARSER_CLASSES, DEFAULT_AUTHENTICATION_CLASSES, EXCEPTION_HANDLER,
# DEFAULT_PERMISSION_CLASSES, DEFAULT_PAGINATION_CLASS, PAGE_SIZE.
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["common.authentication.SessionAuth"],
    "EXCEPTION_HANDLER": "common.errors.handler",
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
# Swagger metadata/assets and the generator that serves our reviewed API contract.
# Set SPECTACULAR_SETTINGS: build a dictionary with named fields such as DEFAULT_GENERATOR_CLASS,
# TITLE, DESCRIPTION, VERSION, SERVE_INCLUDE_SCHEMA, SERVE_PERMISSIONS, SERVE_AUTHENTICATION.
SPECTACULAR_SETTINGS = {
    "DEFAULT_GENERATOR_CLASS": "common.schema.ContractSchemaGenerator",
    "TITLE": "CineScope API",
    "DESCRIPTION": "Backend for the CineScope movie and TV series discovery application.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SERVE_AUTHENTICATION": [],
    "SWAGGER_UI_DIST": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14",
    "SWAGGER_UI_FAVICON_HREF": (
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/favicon-32x32.png"
    ),
}

# CORS permits named browser origins; it does not authenticate users or replace CSRF.
# Set CORS_ALLOWED_ORIGINS: call env.list with the inputs shown; its definition explains the
# checks, side effects and return value.
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
# Set CORS_URLS_REGEX: use the fixed value '^/(api|accounts)/.*$'.
CORS_URLS_REGEX = r"^/(api|accounts)/.*$"
# Set CORS_ALLOW_CREDENTIALS: use the boolean True.
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = False
# Vercel's protocol header is trusted above; browser-supplied forwarded hosts are not.
USE_X_FORWARDED_HOST = False
# Set CSRF_TRUSTED_ORIGINS: call env.list with the inputs shown; its definition explains the
# checks, side effects and return value.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
# Secure cookies travel over HTTPS in production; local HTTP is allowed only with debug enabled.
# Set SESSION_COOKIE_SECURE: evaluate not DEBUG.
SESSION_COOKIE_SECURE = not DEBUG
# Set CSRF_COOKIE_SECURE: evaluate not DEBUG.
CSRF_COOKIE_SECURE = not DEBUG
# Set SESSION_COOKIE_HTTPONLY: use the boolean True.
SESSION_COOKIE_HTTPONLY = True
# Set CSRF_COOKIE_HTTPONLY: use the boolean True.
CSRF_COOKIE_HTTPONLY = True
# Set SECURE_SSL_REDIRECT: evaluate not DEBUG.
SECURE_SSL_REDIRECT = not DEBUG
# Set SECURE_HSTS_SECONDS: choose 31536000 when not DEBUG; otherwise use 0.
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
# Set SECURE_HSTS_INCLUDE_SUBDOMAINS: use the boolean False.
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
# Set SECURE_HSTS_PRELOAD: use the boolean False.
SECURE_HSTS_PRELOAD = False
# Set SECURE_CONTENT_TYPE_NOSNIFF: use the boolean True.
SECURE_CONTENT_TYPE_NOSNIFF = True
# Set SECURE_REFERRER_POLICY: use the fixed value 'same-origin'.
SECURE_REFERRER_POLICY = "same-origin"
# Set X_FRAME_OPTIONS: use the fixed value 'DENY'.
X_FRAME_OPTIONS = "DENY"
# Trust this header only behind Vercel's managed HTTPS proxy.
# Enter this branch only when os.environ.get('VERCEL'). Otherwise execution uses its alternative
# or continues below.
if os.environ.get("VERCEL"):
    # Set SECURE_PROXY_SSL_HEADER: keep these related values together as a tuple:
    # 'HTTP_X_FORWARDED_PROTO', 'https'.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Human-facing React origin: email completion and public collection links point here.
# Set FRONTEND_PUBLIC_ORIGIN: call env('FRONTEND_PUBLIC_ORIGIN', default='http://localhost:5173'
# if DEBUG else '').rstrip with the inputs shown; its definition explains the checks, side effects
# and return value.
FRONTEND_PUBLIC_ORIGIN = env(
    "FRONTEND_PUBLIC_ORIGIN", default="http://localhost:5173" if DEBUG else ""
).rstrip("/")
# Browser-facing API/OAuth origin; with a UI proxy this is the UI host, not the upstream server
# host.
# Set BACKEND_PUBLIC_ORIGIN: call env('BACKEND_PUBLIC_ORIGIN', default='http://localhost:8000' if
# DEBUG else '').rstrip with the inputs shown; its definition explains the checks, side effects
# and return value.
BACKEND_PUBLIC_ORIGIN = env(
    "BACKEND_PUBLIC_ORIGIN", default="http://localhost:8000" if DEBUG else ""
).rstrip("/")
# Enter this branch only when FRONTEND_PUBLIC_ORIGIN and FRONTEND_PUBLIC_ORIGIN not in
# CSRF_TRUSTED_ORIGINS. Otherwise execution uses its alternative or continues below.
if FRONTEND_PUBLIC_ORIGIN and FRONTEND_PUBLIC_ORIGIN not in CSRF_TRUSTED_ORIGINS:
    # Add one item at the end of this list.
    CSRF_TRUSTED_ORIGINS.append(FRONTEND_PUBLIC_ORIGIN)


def validate_origin(value):
    """Origins cannot contain credentials, callback paths, queries or wildcards."""
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.hostname
            and parsed.port != 0
            and not parsed.username
            and not parsed.password
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
            and "*" not in value
            and "\\" not in value
            and not any(character.isspace() for character in value)
            and parsed.scheme in (("http", "https") if DEBUG else ("https",))
        )
    except ValueError:
        valid = False
    if not valid:
        raise ImproperlyConfigured("Use exact HTTP(S) origins; production origins require HTTPS.")


for origin in [
    FRONTEND_PUBLIC_ORIGIN,
    BACKEND_PUBLIC_ORIGIN,
    *CORS_ALLOWED_ORIGINS,
    *CSRF_TRUSTED_ORIGINS,
]:
    if origin:
        validate_origin(origin)
# Set CSRF_FAILURE_VIEW: use the fixed value 'common.middleware.csrf_failure'.
CSRF_FAILURE_VIEW = "common.middleware.csrf_failure"
# Set CSRF_COOKIE_SAMESITE, SESSION_COOKIE_SAMESITE: use the fixed value 'Lax'.
CSRF_COOKIE_SAMESITE = SESSION_COOKIE_SAMESITE = "Lax"
# Set SESSION_COOKIE_AGE: calculate 14 * 86400 from the intermediate values already prepared.
SESSION_COOKIE_AGE = 14 * 86400
# Set SESSION_COOKIE_DOMAIN, CSRF_COOKIE_DOMAIN: use None to represent no known value (JSON null
# at the API boundary).
SESSION_COOKIE_DOMAIN = CSRF_COOKIE_DOMAIN = None
# Django checks local accounts and allauth handles its supported social-account integration.
# Set AUTHENTICATION_BACKENDS: build an ordered list of 2 entries.
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
# Set ACCOUNT_LOGIN_METHODS: evaluate {'email'}.
ACCOUNT_LOGIN_METHODS = {"email"}
# Set ACCOUNT_SIGNUP_FIELDS: build an ordered list of 3 entries.
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
# Set ACCOUNT_EMAIL_VERIFICATION: use the fixed value 'mandatory'.
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
# Set ACCOUNT_ADAPTER: use the fixed value 'accounts.oauth.AccountAdapter'.
ACCOUNT_ADAPTER = "accounts.oauth.AccountAdapter"
# Set SOCIALACCOUNT_ADAPTER: use the fixed value 'accounts.oauth.SocialAdapter'.
SOCIALACCOUNT_ADAPTER = "accounts.oauth.SocialAdapter"
# Set SOCIALACCOUNT_EMAIL_AUTHENTICATION: use the boolean False.
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False
# Set SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT: use the boolean False.
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = False
# Set SOCIALACCOUNT_STORE_TOKENS: use the boolean False.
SOCIALACCOUNT_STORE_TOKENS = False
# Configure only Google from environment values; never paste OAuth secrets into this dictionary.
# Set SOCIALACCOUNT_PROVIDERS: build a dictionary with named fields such as google.
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "provider_class": "accounts.oauth.GoogleProvider",
        "SCOPE": ["openid", "email", "profile"],
        "OAUTH_PKCE_ENABLED": True,
        "APPS": [
            {
                "client_id": env("GOOGLE_CLIENT_ID", default=""),
                "secret": env("GOOGLE_CLIENT_SECRET", default=""),
                "key": "",
            }
        ],
    }
}
# Set SOCIALACCOUNT_REQUESTS_TIMEOUT: use the fixed value 5.
SOCIALACCOUNT_REQUESTS_TIMEOUT = 5
# Set LOGIN_REDIRECT_URL: use the fixed value '/discover'.
LOGIN_REDIRECT_URL = "/discover"
# Console delivery is local-only; production needs real SMTP or another configured delivery
# backend.
# Set EMAIL_BACKEND: call env with the inputs shown; its definition explains the checks, side
# effects and return value.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend"
    if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend",
)
# Set EMAIL_HOST: call env with the inputs shown; its definition explains the checks, side effects
# and return value.
EMAIL_HOST = env("EMAIL_HOST", default="")
# Set EMAIL_PORT: convert to a whole number; invalid text raises an error handled by the
# surrounding code.
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
# Set EMAIL_HOST_USER: call env with the inputs shown; its definition explains the checks, side
# effects and return value.
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
# Set EMAIL_HOST_PASSWORD: call env with the inputs shown; its definition explains the checks,
# side effects and return value.
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
# Set EMAIL_USE_TLS: reduce the value to a true/false test rather than returning the original
# object.
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
# Set EMAIL_TIMEOUT: use the fixed value 5.
EMAIL_TIMEOUT = 5
# Set DEFAULT_FROM_EMAIL: call env with the inputs shown; its definition explains the checks, side
# effects and return value.
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="cinescope@localhost")
# External metadata settings are server-only. React never receives these credentials.
# Set TMDB_BASE_URL: call env('TMDB_BASE_URL', default='https://api.themoviedb.org/3').rstrip with
# the inputs shown; its definition explains the checks, side effects and return value.
TMDB_BASE_URL = env("TMDB_BASE_URL", default="https://api.themoviedb.org/3").rstrip("/")
if TMDB_BASE_URL != "https://api.themoviedb.org/3":
    raise ImproperlyConfigured("TMDB_BASE_URL must use the trusted TMDB API origin and /3 path.")
# Set TMDB_READ_ACCESS_TOKEN: call env with the inputs shown; its definition explains the checks,
# side effects and return value.
TMDB_READ_ACCESS_TOKEN = env("TMDB_READ_ACCESS_TOKEN", default="")
# Set TMDB_API_KEY: call env with the inputs shown; its definition explains the checks, side
# effects and return value.
TMDB_API_KEY = env("TMDB_API_KEY", default="")
# Use a separate stable encryption key to recover active owner share links across deployments.
# Set SHARE_TOKEN_ENCRYPTION_KEY: call env with the inputs shown; its definition explains the
# checks, side effects and return value.
SHARE_TOKEN_ENCRYPTION_KEY = env("SHARE_TOKEN_ENCRYPTION_KEY", default="")
# Shared database cache survives across serverless instances; process memory alone would not.
# Set CACHES: build a dictionary with named fields such as default.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cinescope_cache",
        "TIMEOUT": 300,
        "OPTIONS": {"MAX_ENTRIES": 10000},
    }
}
# Set API_THROTTLING_ENABLED: use the boolean True.
API_THROTTLING_ENABLED = True
# Bound request-body memory use, especially when a guest submits a saved library.
# Set DATA_UPLOAD_MAX_MEMORY_SIZE: use the fixed value 1048576.
DATA_UPLOAD_MAX_MEMORY_SIZE = 1048576

# Send useful logs to the console while redacting capability/OAuth query values.
# Set LOGGING: build a dictionary with named fields such as version, disable_existing_loggers,
# filters, formatters, handlers, root, loggers.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"redact": {"()": "common.logging.RedactCapabilities"}},
    "formatters": {
        "standard": {
            "()": "common.logging.SafeFormatter",
            "format": "{asctime} {levelname} {name}: {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "filters": ["redact"],
        }
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {"django": {"handlers": ["console"], "level": "INFO", "propagate": False}},
}
# HTTP client URLs can contain credential query parameters; don't log them.
# Write these fields directly on the matching rows through the orm.
LOGGING["loggers"].update(
    {
        name: {"handlers": ["console"], "level": "WARNING", "propagate": False}
        for name in ("httpx", "httpcore", "allauth", "django.server")
    }
)
