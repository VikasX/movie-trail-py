# FILE PURPOSE: Reads normal Django session cookies and gives anonymous API failures the agreed
# 401 behavior.
# Import SessionAuthentication from rest_framework.authentication (DRF request/response helpers).
from rest_framework.authentication import SessionAuthentication


# Keeps Django cookie authentication while adapting anonymous API errors to our 401 contract.
class SessionAuth(SessionAuthentication):
    # Supply an authentication label so DRF can return 401 rather than converting it to 403.
    def authenticate_header(self, request):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context.
        # Return the result to the caller: use the fixed value 'Session'.
        return "Session"
