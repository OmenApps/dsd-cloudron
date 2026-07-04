from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class NoSignupAccountAdapter(DefaultAccountAdapter):
    """Disable self-service local registration; Cloudron OIDC is the way in."""

    def is_open_for_signup(self, request):
        return False


class CloudronSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Keep first-login OIDC provisioning working; do not delegate to the account adapter."""

    def is_open_for_signup(self, request, sociallogin):
        return True
