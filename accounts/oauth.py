# FILE PURPOSE: Connects our Google-start endpoint to allauth; allauth performs the OAuth
# callback.
# Import urlencode from urllib.parse (the named Python helper module).
from urllib.parse import urlencode

# Import DefaultAccountAdapter from allauth.account.adapter (the maintained account/Google
# integration).
from allauth.account.adapter import DefaultAccountAdapter

# Import ImmediateHttpResponse from allauth.core.exceptions (the maintained account/Google
# integration).
from allauth.core.exceptions import ImmediateHttpResponse

# Import DefaultSocialAccountAdapter from allauth.socialaccount.adapter (the maintained
# account/Google integration).
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

# Import GoogleProvider from allauth.socialaccount.providers.google.provider (the maintained
# account/Google integration).
from allauth.socialaccount.providers.google.provider import GoogleProvider as BaseGoogleProvider

# Import GoogleOAuth2Adapter from allauth.socialaccount.providers.google.views (the maintained
# account/Google integration).
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter

# Import OAuth2CallbackView from allauth.socialaccount.providers.oauth2.views (the maintained
# account/Google integration).
from allauth.socialaccount.providers.oauth2.views import OAuth2CallbackView

# Import settings from django.conf (Django framework/database/security helpers).
from django.conf import settings

# Import get_user_model from django.contrib.auth (Django framework/database/security helpers).
from django.contrib.auth import get_user_model

# Import HttpResponseRedirect, JsonResponse from django.http (Django framework/database/security
# helpers).
from django.http import HttpResponseRedirect, JsonResponse

# Import APIError from common.errors (our shared API layer).
from common.errors import APIError


# Build a frontend return URL from a small allowlist; never redirect to an arbitrary caller URL.
def frontend_redirect(request, outcome):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; outcome = argument supplied
    # by the caller.
    # path holds the route to request externally or the frontend completion path; read the
    # surrounding function for its role. Next, look up a named setting/value or make the indicated
    # GET call; the surrounding object determines which.
    path = request.session.get("oauth_return_to", "/discover")
    # Enter this branch only when path not in ('/discover', '/library'). Otherwise execution uses
    # its alternative or continues below.
    if path not in ("/discover", "/library"):
        # path holds the route to request externally or the frontend completion path; read the
        # surrounding function for its role. Next, use the fixed value '/discover'.
        path = "/discover"
    # Return the result to the caller: calculate settings.FRONTEND_PUBLIC_ORIGIN + path + '?' +
    # urlencode({'auth': outcome}) from the intermediate values already prepared.
    return settings.FRONTEND_PUBLIC_ORIGIN + path + "?" + urlencode({"auth": outcome})


class AccountAdapter(DefaultAccountAdapter):
    # Return the approved frontend location after allauth finishes an existing-account login.
    def get_login_redirect_url(self, request):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context.
        # Return the result to the caller: call frontend_redirect with the inputs shown; its
        # definition explains the checks, side effects and return value.
        return frontend_redirect(request, "success")

    # Use the same frontend completion behavior for a newly created Google account.
    def get_signup_redirect_url(self, request):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context.
        # Return the result to the caller: call frontend_redirect with the inputs shown; its
        # definition explains the checks, side effects and return value.
        return frontend_redirect(request, "success")


class CanonicalGoogleAdapter(GoogleOAuth2Adapter):
    # Use the configured public backend/proxy origin for the exact registered Google callback
    # path.
    def get_callback_url(self, request, app):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context; app = argument supplied by the caller.
        # Enter this branch only when not settings.BACKEND_PUBLIC_ORIGIN. Otherwise execution uses
        # its alternative or continues below.
        if not settings.BACKEND_PUBLIC_ORIGIN:
            # Stop this action with safe API error 'service_unavailable' (HTTP 503). The common
            # handler builds its JSON envelope.
            raise APIError("service_unavailable", "Public OAuth origin is not configured.", 503)
        # Return the result to the caller: calculate settings.BACKEND_PUBLIC_ORIGIN +
        # '/accounts/google/login/callback/' from the intermediate values already prepared.
        return settings.BACKEND_PUBLIC_ORIGIN + "/accounts/google/login/callback/"


class GoogleProvider(BaseGoogleProvider):
    # Set oauth2_adapter_class: reuse CanonicalGoogleAdapter, which was prepared earlier in this
    # function.
    oauth2_adapter_class = CanonicalGoogleAdapter


class SocialAdapter(DefaultSocialAccountAdapter):
    # Require a Google-verified email and block silent linking to an existing local account.
    def pre_social_login(self, request, sociallogin):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context; sociallogin = argument supplied by the caller.
        # verified holds Google-supplied email identities marked verified; an unverified assertion
        # is not enough for login. Next, build a list for each e in sociallogin.email_addresses;
        # keep only entries passing e.verified.
        verified = [e for e in sociallogin.email_addresses if e.verified]
        # Enter this branch only when not verified. Otherwise execution uses its alternative or
        # continues below.
        if not verified:
            # Raise ImmediateHttpResponse; normal execution of this block stops here.
            raise ImmediateHttpResponse(
                HttpResponseRedirect(frontend_redirect(request, "verified_email_required"))
            )
        # Enter this branch only when sociallogin.is_existing. Otherwise execution uses its
        # alternative or continues below.
        if sociallogin.is_existing:
            # Exit this function now without a result; no remaining statements in this function
            # run.
            return
        # Enter this branch only when
        # get_user_model().objects.filter(email__iexact=verified[0].email).exists(). Otherwise
        # execution uses its alternative or continues below.
        if get_user_model().objects.filter(email__iexact=verified[0].email).exists():
            # Raise ImmediateHttpResponse; normal execution of this block stops here.
            raise ImmediateHttpResponse(
                HttpResponseRedirect(frontend_redirect(request, "account_link_required"))
            )
        # Set sociallogin.user.email: call verified[0].email.strip().casefold with the inputs
        # shown; its definition explains the checks, side effects and return value.
        sociallogin.user.email = verified[0].email.strip().casefold()

    # Turn Google cancellation/failure into a safe redirect, or reject invalid state with JSON.
    def on_authentication_error(
        self, request, provider, error=None, exception=None, extra_context=None
    ):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context; provider = argument supplied by the caller; error = argument supplied by the
        # caller; exception = argument supplied by the caller; extra_context = argument supplied
        # by the caller.
        # Enter this branch only when not (extra_context or {}).get('state'). Otherwise execution
        # uses its alternative or continues below.
        if not (extra_context or {}).get("state"):
            # response holds the response produced by the next handler or external HTTP request.
            # Next, call JsonResponse with the inputs shown; its definition explains the checks,
            # side effects and return value.
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
            # response holds the response produced by the next handler or external HTTP request.
            # Next, call HttpResponseRedirect with the inputs shown; its definition explains the
            # checks, side effects and return value.
            response = HttpResponseRedirect(
                frontend_redirect(request, "cancelled" if str(error) == "cancelled" else "failed")
            )
        # Raise ImmediateHttpResponse; normal execution of this block stops here.
        raise ImmediateHttpResponse(response)

    # Let allauth save the new social account, then create its application preferences.
    def save_user(self, request, sociallogin, form=None):
        # INPUTS TO THIS FUNCTION: self = this class instance; request = current browser/user
        # context; sociallogin = argument supplied by the caller; form = argument supplied by the
        # caller.
        # Import UserPreferences from accounts.models (our account layer).
        from accounts.models import UserPreferences

        # user holds the Django account involved in this action; do not confuse it with the
        # client-submitted email string. Next, call super().save_user with the inputs shown; its
        # definition explains the checks, side effects and return value.
        user = super().save_user(request, sociallogin, form)
        # Reuse a matching row or insert one; the second returned value says whether it was newly
        # created.
        UserPreferences.objects.get_or_create(
            user=user, defaults={"display_name": user.get_full_name()[:80]}
        )
        # Return the result to the caller: reuse user, which was prepared earlier in this
        # function.
        return user


# Ask allauth to construct Google authorization/state/PKCE and return the browser navigation
# URL.
def start(request, params, data):
    # INPUTS TO THIS FUNCTION: request = current browser/user context; params = cleaned URL/query
    # values; data = validated JSON.
    # Import get_adapter from allauth.socialaccount.adapter (the maintained account/Google
    # integration).
    from allauth.socialaccount.adapter import get_adapter

    # provider_settings holds the configured Google application values, loaded from environment
    # settings. Next, read the entry indexed by 0 from
    # settings.SOCIALACCOUNT_PROVIDERS['google']['APPS'].
    provider_settings = settings.SOCIALACCOUNT_PROVIDERS["google"]["APPS"][0]
    # Enter this branch only when not all((provider_settings['client_id'],
    # provider_settings['secret'], settings.FRONTEND_PUBLIC_ORIGIN,
    # settings.BACKEND_PUBLIC_ORIGIN)). Otherwise execution uses its alternative or continues
    # below.
    if not all(
        (
            provider_settings["client_id"],
            provider_settings["secret"],
            settings.FRONTEND_PUBLIC_ORIGIN,
            settings.BACKEND_PUBLIC_ORIGIN,
        )
    ):
        # Stop this action with safe API error 'service_unavailable' (HTTP 503). The common
        # handler builds its JSON envelope.
        raise APIError("service_unavailable", "Google OAuth is not configured.", 503)
    # raw holds the source value before this step converts or normalizes it. Next, read
    # request._request from the indicated object.
    raw = request._request
    # Set raw.session['oauth_return_to']: look up a named setting/value or make the indicated GET
    # call; the surrounding object determines which.
    raw.session["oauth_return_to"] = data.get("return_to", "/discover")
    # provider holds allauth Google provider object; it owns authorization/state/PKCE
    # construction. Next, call get_adapter(raw).get_provider with the inputs shown; its definition
    # explains the checks, side effects and return value.
    provider = get_adapter(raw).get_provider(raw, provider="google")
    # response holds the response produced by the next handler or external HTTP request. Next,
    # call provider.redirect with the inputs shown; its definition explains the checks, side
    # effects and return value.
    response = provider.redirect(raw, process="login")
    # Enter this branch only when response.status_code != 302. Otherwise execution uses its
    # alternative or continues below.
    if response.status_code != 302:
        # Stop this action with safe API error 'service_unavailable' (HTTP 503). The common
        # handler builds its JSON envelope.
        raise APIError("service_unavailable", "Unable to start OAuth.", 503)
    # Return this named-field dictionary; API handlers turn it into JSON, while helper callers use
    # it directly.
    return {"authorization_url": response["Location"]}


# Use allauth's complete callback lifecycle at its conventional path, with only
# the canonical externally registered redirect URI overridden in its adapter.
# Set callback: call OAuth2CallbackView.adapter_view with the inputs shown; its definition
# explains the checks, side effects and return value.
callback = OAuth2CallbackView.adapter_view(CanonicalGoogleAdapter)
