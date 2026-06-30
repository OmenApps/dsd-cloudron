# Scaffold a new project

This guide is for starting a brand new Django project that deploys to
Cloudron from the start. If you already have a project, see
{doc}`retrofit-existing-project` instead - `dsd-cloudron new` generates a
fresh project tree and will not touch one that already exists.

## Generate the project

```bash
dsd-cloudron new "My App"
cd my_app
```

The argument is a human-readable project name; it gets slugged into the
Python package name (`my_app` here) and the Cloudron app id. Use
`--output-dir` to create the project somewhere other than the current
directory.

The command produces a ready-to-install Django project: the project and
app code, local development tooling, and the same Cloudron artifact set a
retrofit deploy would generate - manifest, Dockerfile, `start.sh`,
supervisor configs, nginx config, and settings glue - all rendered up
front. There is nothing further to run before `cloudron install`.

## Toggles

Infra addons are on by default, same as retrofit; disable what you do not
need:

`--no-redis`
: Skip the Redis addon and cache configuration.

`--no-sendmail`
: Skip the sendmail addon.

Everything else is opt-in and off by default:

`--celery`
: Add a Celery worker and beat process, with `celery.py` generated and
  already imported in the project's `__init__.py`.

`--sso`
: Add the Cloudron OIDC addon and django-allauth, fully wired into
  `INSTALLED_APPS`, middleware, and `urls.py`.

`--ninja`
: Add a django-ninja API app and mount it at `/api/`.

`--htmx`
: Add django-htmx, django-crispy-forms, and the Bootstrap 5 crispy
  template pack.

`--s3`
: Add django-storages and an S3-compatible media backend, active once you
  set `AWS_STORAGE_BUCKET_NAME` on the server.

As with retrofit, `--celery` requires Redis, so combining it with
`--no-redis` is rejected before anything is written.

This is the main difference from retrofit: scaffolding wires `--celery`
and `--sso` straight into the generated code, because there is no existing
URLconf or app list to risk breaking. A retrofit deploy can only add the
packages and configuration; you finish wiring allauth into your own
project by hand.

## What you get

The generated project is a standard Django layout with a few pieces
specific to Cloudron:

- An `accounts` app with a custom `User` model, so the project can
  evolve its auth setup later without a disruptive migration.
- A `core` app with a landing-page view at `/` and a health-check view
  mounted at `/healthz/` - the same path the generated
  `CloudronManifest.json` is configured to poll, so the app passes its
  health check the moment it starts.
- `settings.py` split into local-development defaults (SQLite, an
  insecure dev `SECRET_KEY`) and a generated `cloudron_settings.py`
  import, gated on the `CLOUDRON_APP_ORIGIN` environment variable so it
  only takes effect on Cloudron.
- `docker-compose.yml` and `Dockerfile.dev` for local development against
  real Postgres and Redis services, plus a `pyproject.toml` set up for
  `uv`.
- A `README.md` that points to the generated `README-cloudron.md` as the
  deploy control surface - the file to read for what each Cloudron
  artifact controls and how to change it.

The generated-files reference covers the full artifact set and what each
file does; the CLI reference lists every `new` flag.

## Install it

```bash
cloudron install -l my-app
```

From here, iterating looks the same as it does for a retrofit deploy:
edit code or settings, then `cloudron update`. See the quickstart for the
first-sign-in steps after install.
