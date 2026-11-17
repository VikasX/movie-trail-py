from urllib.parse import urlencode

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.providers.google.provider import GoogleProvider as BaseGoogleProvider
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.views import OAuth2CallbackView
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect, JsonResponse

from common.errors import APIError


def frontend_redirect(request, outcome):
    path = request.session.get("oauth_return_to", "/discover")
    if path not in ("/discover", "/library"):
        path = "/discover"
    return settings.FRONTEND_PUBLIC_ORIGIN + path + "?" + urlencode({"auth": outcome})


class AccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        return frontend_redirect(request, "success")

    def get_signup_redirect_url(self, request):
        return frontend_redirect(request, "success")


class CanonicalGoogleAdapter(GoogleOAuth2Adapter):
    def get_callback_url(self, request, app):
        if not settings.BACKEND_PUBLIC_ORIGIN:
            raise APIError("service_unavailable", "Public OAuth origin is not configured.", 503)
        return settings.BACKEND_PUBLIC_ORIGIN + "/accounts/google/login/callback/"


class GoogleProvider(BaseGoogleProvider):
    oauth2_adapter_class = CanonicalGoogleAdapter


class SocialAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        verified = [e for e in sociallogin.email_addresses if e.verified]
        if not verified:
            raise ImmediateHttpResponse(
                HttpResponseRedirect(frontend_redirect(request, "verified_email_required"))
            )
        if sociallogin.is_existing:
            return
        if get_user_model().objects.filter(email__iexact=verified[0].email).exists():
            raise ImmediateHttpResponse(
                HttpResponseRedirect(frontend_redirect(request, "account_link_required"))
            )
        sociallogin.user.email = verified[0].email.strip().casefold()

    def on_authentication_error(
        self, request, provider, error=None, exception=None, extra_context=None
    ):
        if not (extra_context or {}).get("state"):
            response = JsonResponse(
                {
                    "error": {
                        "code": "invalid_state",
                        "message": "Invalid or expired OAuth state.",
                        "fields": {},
                        "request_id": getattr(request, "request_id", ""),
                    }
                },
                status=400,
            )
        else:
            response = HttpResponseRedirect(
                frontend_redirect(request, "cancelled" if str(error) == "cancelled" else "failed")
            )
        raise ImmediateHttpResponse(response)

    def save_user(self, request, sociallogin, form=None):
        from accounts.models import UserPreferences

        user = super().save_user(request, sociallogin, form)
        UserPreferences.objects.get_or_create(
            user=user, defaults={"display_name": user.get_full_name()[:80]}
        )
        return user


def start(request, params, data):
    from allauth.socialaccount.adapter import get_adapter

    provider_settings = settings.SOCIALACCOUNT_PROVIDERS["google"]["APPS"][0]
    if not all(
        (
            provider_settings["client_id"],
            provider_settings["secret"],
            settings.FRONTEND_PUBLIC_ORIGIN,
            settings.BACKEND_PUBLIC_ORIGIN,
        )
    ):
        raise APIError("service_unavailable", "Google OAuth is not configured.", 503)
    raw = request._request
    raw.session["oauth_return_to"] = data.get("return_to", "/discover")
    provider = get_adapter(raw).get_provider(raw, provider="google")
    response = provider.redirect(raw, process="login")
    if response.status_code != 302:
        raise APIError("service_unavailable", "Unable to start OAuth.", 503)
    return {"authorization_url": response["Location"]}


# Use allauth's complete callback lifecycle at its conventional path, with only
# the canonical externally registered redirect URI overridden in its adapter.
callback = OAuth2CallbackView.adapter_view(CanonicalGoogleAdapter)
