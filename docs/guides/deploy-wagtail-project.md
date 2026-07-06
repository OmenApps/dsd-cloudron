# Deploy a Wagtail project

`--wagtail` configures an existing [Wagtail](https://wagtail.org) project for
Cloudron. It is a retrofit-only flag on `python manage.py deploy`: it renders the
Cloudron settings glue a Wagtail site needs, raises the default memory limit, and
prints the wiring steps that stay yours to apply. The plain-Django deploy is
unchanged; `--wagtail` only adds to it.

## Build a project to deploy

Start from a stock Wagtail project if you do not already have one:

```bash
pip install wagtail
wagtail start blog
cd blog
```

A `wagtail start` project uses a settings *package* - `blog/settings/base.py`,
`dev.py`, and `production.py` - and its `wsgi.py` and `manage.py` default
`DJANGO_SETTINGS_MODULE` to `blog.settings.dev`. That split matters on Cloudron;
see [Split settings](#split-settings) below.

## Deploy

```bash
python manage.py deploy --location blog --wagtail
```

The `--wagtail` flag makes the deploy:

- Set `WAGTAILADMIN_BASE_URL` from `CLOUDRON_APP_ORIGIN` in `cloudron_settings.py`,
  so the admin builds correct absolute URLs (password-reset emails, previews)
  against the app's real Cloudron domain.
- Force Wagtail search onto the database backend (Postgres full-text) with a
  `WAGTAILSEARCH_BACKENDS` override. Cloudron has no Elasticsearch or OpenSearch
  addon, so an Elasticsearch/OpenSearch backend in your project would fail to
  connect at runtime; the override keeps search working on the Postgres addon
  every Cloudron app already gets.
- Raise the default `memoryLimit` to about 1.5 GB (from 1 GB). Wagtail's admin and
  Pillow-based image rendition generation need more headroom than a bare Django
  app. An explicit `--memory-limit` always wins; raise it further if bulk media
  import runs the app out of memory.

Both settings land inside the `if os.environ.get("CLOUDRON_APP_ORIGIN"):` gate, so
they are inert during local development and the image build.

### Add `django.contrib.postgres`

The Postgres database search backend requires `django.contrib.postgres` in your
`INSTALLED_APPS`. The plugin does not edit your `settings.py`, so add it yourself:

```python
INSTALLED_APPS = [
    # ...
    "django.contrib.postgres",
]
```

### Populate the search index

If your site already has content when you retrofit it (for example you were
running Elasticsearch before), run the index build once after the first deploy so
search returns results:

```bash
cloudron exec --app blog -- python3 /app/code/manage.py update_index
```

A brand-new site has nothing to index yet; Wagtail updates the index as you add
pages.

## Health check stays at `/`

`--wagtail` deliberately does not change the health check path. A stock Wagtail
site serves its home page - a 200 - at `/`, which is exactly what the Cloudron
health check needs, so nothing extra is required for a single-language site. This
is the same reason the plain-Django default works: the health probe carries the
app domain as its `Host`, so `ALLOWED_HOSTS = [CLOUDRON_APP_DOMAIN]` matches.

Only a multilingual site that redirects `/` needs a dedicated health endpoint; see
[Multilingual sites](#multilingual-sites).

## Signing in

A local `admin` superuser is created on the first install, with a generated
password saved on the server at `/app/data/.initial_admin_password` (read it with
`cloudron exec` during the first-boot window - it is removed on the next start).
Sign in to the Wagtail admin at `/admin/`. Django's own admin, if you enable it,
is at `/django-admin/`.

## Media and renditions persist

Uploaded images and documents, and the cached renditions Wagtail generates from
them, write to `/app/data/media` (set as `MEDIA_ROOT` in `cloudron_settings.py`).
`/app/data` is the one writable, backed-up volume on Cloudron, so your media and
renditions survive `cloudron update` and are included in backups.

## Multilingual sites

Multilingual wiring is an explicit opt-in - the plugin never touches your
`settings.py` or `urls.py`, so these edits are yours. The deploy also mirrors these
steps into `CLOUDRON_NEXT_STEPS.md` next to your project, so you have them after the
output scrolls away.

Install `wagtail-localize`, then in `settings.py`:

```python
USE_I18N = True
WAGTAIL_I18N_ENABLED = True
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("es", "Spanish")]
WAGTAIL_CONTENT_LANGUAGES = LANGUAGES

INSTALLED_APPS = [
    # ...
    "wagtail_localize",
    "wagtail_localize.locales",  # use instead of "wagtail.locales" - remove that one
]

# after SessionMiddleware and before CommonMiddleware:
MIDDLEWARE = [
    # ...
    "django.middleware.locale.LocaleMiddleware",
]
```

In `urls.py`, DELETE the stock non-prefixed catch-all
`path("", include(wagtail_urls))` and replace it with the `i18n_patterns` form. Keep
`admin/` and `documents/` above it and *outside* `i18n_patterns`; move any `search/`
route *inside* `i18n_patterns` (above the catch-all) so it is translated per language
too, matching Wagtail's own i18n layout:

```python
from django.conf.urls.i18n import i18n_patterns
from wagtail import urls as wagtail_urls  # if not already imported

urlpatterns += i18n_patterns(
    # keep your existing search/ route here, above the catch-all
    path("", include(wagtail_urls)), prefix_default_language=False
)
```

Run `python manage.py migrate` locally to create wagtail-localize's tables, and
create a `Locale` record for each non-default language (Wagtail admin, Settings,
Locales) or `/es/` will 404.

`prefix_default_language=False` is the simple path: it keeps `/` serving your
default language (a 200), so the health check can stay `/` and you need no health
view. If instead you prefix *every* language (`prefix_default_language=True`, the
Django default), `/` becomes a 302 to `/en/` and fails the Cloudron health check.
Then add a liveness endpoint outside `i18n_patterns` and re-deploy pointing the
health check at it:

```python
from django.http import HttpResponse

urlpatterns = [path("healthz/", lambda r: HttpResponse("ok")), *urlpatterns]
```

```bash
python manage.py deploy --location blog --wagtail --health-check-path /healthz/
```

(That view is liveness only - it returns 200 without checking the database.)

## Celery with Wagtail

`--wagtail --celery` works. The container pins `DJANGO_SETTINGS_MODULE` to the
production settings module (see [Split settings](#split-settings)), so the Celery
worker and beat load the same gated settings gunicorn does - including the Redis
broker - rather than the ungated `dev` settings.

(split-settings)=
## Split settings

A stock `wagtail start` project uses a settings package whose `wsgi.py`,
`manage.py`, and `celery.py` default `DJANGO_SETTINGS_MODULE` to
`blog.settings.dev`. django-simple-deploy appends
`from blog.cloudron_settings import *` to `blog/settings/production.py` (its
`_get_settings_path` targets `production` for a split-settings project), and
dsd-cloudron pins `DJANGO_SETTINGS_MODULE=blog.settings.production` in the
container's `start.sh`. So gunicorn, the `migrate`/`collectstatic` calls, and
celery all load the gated production settings and `DEBUG=False` holds.

django-simple-deploy detects this split-settings layout on its own, so the
settings-module pin happens whether or not you pass `--wagtail`. The Wagtail glue
(`WAGTAILADMIN_BASE_URL`, the database search backend, the raised memory limit) does
*not* - it needs the flag. Deploy a Wagtail project without `--wagtail` and the
deploy warns you it was skipped; re-run with the flag to apply it.

Keep your `settings/production.py` deploy-ready: in particular, it should not
hard-require at import time an environment variable that only the Cloudron gate
sets - the gate is appended last, so a top-level `os.environ["..."]` above it would
fail the build. If you need to patch something the plugin does not, drop a
`/app/data/custom_settings.py` on the server (owned by `root`, mode 640); it is
imported last, so it can even re-point search at a network-reachable external
Elasticsearch if you have one.

## Reconfigure

A `deploy --reconfigure` re-renders the Cloudron artifacts with a per-file diff
you approve. It preserves the deployed `memoryLimit` and `healthCheckPath` from the
manifest (not from the flags), and it preserves the Wagtail settings block, which
it reconstructs from `cloudron_settings.py` - so you do *not* need to re-pass
`--wagtail` on a reconfigure. Change sizing by editing `CloudronManifest.json` or
re-deploying.
