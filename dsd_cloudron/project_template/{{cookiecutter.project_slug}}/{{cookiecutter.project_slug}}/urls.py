from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", include("{{ cookiecutter.project_slug }}.core.urls")),
{% if cookiecutter.use_sso == "yes" %}    path("accounts/", include("allauth.urls")),
{% endif %}{% if cookiecutter.use_ninja == "yes" %}    path("api/", __import__("{{ cookiecutter.project_slug }}.core.api", fromlist=["api"]).api.urls),
{% endif %}]
