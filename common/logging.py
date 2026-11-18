# FILE PURPOSE: Hides share capabilities and sensitive OAuth/query values before console
# logging.
# Import logging so the code below can use that module namespace.
import logging

# Import re so the code below can use that module namespace.
import re


class RedactCapabilities(logging.Filter):
    # Scrub sensitive values from the log message before the console handler prints it.
    def filter(self, record):
        # INPUTS TO THIS FUNCTION: self = this class instance; record = argument supplied by the
        # caller.
        # Set message: call record.getMessage with the inputs shown; its definition explains the
        # checks, side effects and return value.
        message = record.getMessage()
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
