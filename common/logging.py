# FILE PURPOSE: Hides share capabilities and sensitive OAuth/query values before console
# logging.
# Import logging so the code below can use that module namespace.
import logging

# Import re so the code below can use that module namespace.
import re

from django.conf import settings


def redact(message):
    """Scrub capabilities, credentials and cookies, including exception text."""
    message = re.sub(r"(/(?:api/v1/)?shared/)[^/?\s]+", r"\1[redacted]", message)
    message = re.sub(
        r"([?&](?:token|code|state|api_key|access_token|id_token)=)[^&\s]+",
        r"\1[redacted]",
        message,
        flags=re.IGNORECASE,
    )
    message = re.sub(r"\bBearer\s+[^\s,'\"}]+", "Bearer [redacted]", message, flags=re.IGNORECASE)
    message = re.sub(r"(postgres(?:ql)?://)[^\s'\"]+", r"\1[redacted]", message)
    message = re.sub(r"((?:sessionid|csrftoken)=)[^;\s,'\"]+", r"\1[redacted]", message)
    # Exact-value redaction also covers secrets inside unusual exception formats.
    values = [
        getattr(settings, name, "")
        for name in (
            "SECRET_KEY",
            "TMDB_READ_ACCESS_TOKEN",
            "TMDB_API_KEY",
            "GOOGLE_CLIENT_SECRET",
            "SHARE_TOKEN_ENCRYPTION_KEY",
            "EMAIL_HOST_PASSWORD",
        )
    ]
    values += [settings.DATABASES.get("default", {}).get("PASSWORD", "")]
    google = getattr(settings, "SOCIALACCOUNT_PROVIDERS", {}).get("google", {})
    values += [app.get("secret", "") for app in google.get("APPS", [])]
    for value in values:
        if isinstance(value, str) and value:
            message = message.replace(value, "[redacted]")
    return message


class SafeFormatter(logging.Formatter):
    def format(self, record):
        # Filters run before Python appends traceback text. Redact the final output too.
        return redact(super().format(record))


class RedactCapabilities(logging.Filter):
    # Scrub sensitive values from the log message before the console handler prints it.
    def filter(self, record):
        # INPUTS TO THIS FUNCTION: self = this class instance; record = argument supplied by the
        # caller.
        # Set message: call record.getMessage with the inputs shown; its definition explains the
        # checks, side effects and return value.
        message = redact(record.getMessage())
        # Set message: call re.sub with the inputs shown; its definition explains the checks, side
        # effects and return value.
        message = re.sub(r"(/api/v1/shared/)[^/?\s]+", r"\1[redacted]", message)
        # Set message: call re.sub with the inputs shown; its definition explains the checks, side
        # effects and return value.
        message = re.sub(r"([?&](?:token|code|state|api_key)=)[^&\s]+", r"\1[redacted]", message)
        # Set record.msg: reuse message, which was prepared earlier in this function.
        record.msg = message
        # Set record.args: keep these related values together as a tuple: .
        record.args = ()
        # Return True to report that this predicate/check passed.
        return True
