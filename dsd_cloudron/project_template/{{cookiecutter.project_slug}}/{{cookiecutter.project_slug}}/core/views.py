from django.http import HttpResponse


def home(request):
    """Landing page at /, so the app root and the post-login redirect resolve.

    LOGIN_REDIRECT_URL is "/", so without a root route every sign-in (including
    Cloudron SSO) lands on a 404. Replace this with your own homepage.
    """
    return HttpResponse(
        "<h1>{{ cookiecutter.project_name }}</h1>"
        "<p>This Django project is running on Cloudron. "
        "Edit core/views.py to replace this page.</p>",
        content_type="text/html",
    )


def healthz(request):
    """200 response for the Cloudron health check."""
    return HttpResponse("ok", content_type="text/plain")
