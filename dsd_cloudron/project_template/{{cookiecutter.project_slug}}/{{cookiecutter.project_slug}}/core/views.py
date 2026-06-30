from django.http import HttpResponse


def home(request):
    """Landing page at /, so the app root resolves instead of returning a 404.

    When SSO is enabled LOGIN_REDIRECT_URL is "/", so the post-login redirect also
    lands here; without a root route it would 404. Replace this with your homepage.
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
