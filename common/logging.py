import logging
import re


class RedactCapabilities(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        message = re.sub(r"(/api/v1/shared/)[^/?\s]+", r"\1[redacted]", message)
        message = re.sub(r"([?&](?:token|code|state|api_key)=)[^&\s]+", r"\1[redacted]", message)
        record.msg = message
        record.args = ()
        return True
