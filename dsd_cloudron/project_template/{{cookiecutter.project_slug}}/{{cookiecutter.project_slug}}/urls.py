from django.contrib import admin
from django.urls import include, path

from {{ cookiecutter.project_slug }}.core.views import home
{% if cookiecutter.use_ninja == "yes" %}
from {{ cookiecutter.project_slug }}.core.api import api
{% endif %}
urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin.site.urls),
    path("healthz/", include("{{ cookiecutter.project_slug }}.core.urls")),
{% if cookiecutter.use_sso == "yes" %}    path("accounts/", include("allauth.urls")),
{% endif %}{% if cookiecutter.use_ninja == "yes" %}    path("api/", api.urls),
{% endif %}]
