from rest_framework.authentication import SessionAuthentication


class SessionAuth(SessionAuthentication):
    def authenticate_header(self, request):
        return "Session"
