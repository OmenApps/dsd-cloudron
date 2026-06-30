# Retrofit an existing project

This guide is for an existing Django project that you want to deploy to
Cloudron. If you are starting from nothing, {doc}`scaffold-new-project` is
the faster path - it generates a project with the same Cloudron wiring
already in place.

Install `dsd-cloudron` and authenticate with your Cloudron server first (see
the installation guide), then run the deploy command from your project root.

## Config only

```bash
python manage.py deploy --location blog
```

`--location` is the Cloudron subdomain you intend to install to, e.g.
`blog` for `blog.example.com`. With config only, `manage.py deploy` writes
the Cloudron artifacts and modifies your settings file but does not build
or install anything - review the changes, commit them, and run
`cloudron install` yourself when ready.

## Config and install

Add the django-simple-deploy core flag `--automate-all`:

```bash
python manage.py deploy --location blog --automate-all
```

`--automate-all` is not a dsd-cloudron flag - it belongs to django-simple-deploy
itself and works the same way across every platform plugin. With it set,
the command also commits the generated files and runs the Cloudron build
and install for you. Every other flag covered on this page - `--location`,
`--app-id`, `--memory-limit`, `--health-check-path`, `--celery`, `--sso` -
belongs to dsd-cloudron specifically; the {doc}`/reference/cli` lists the
full set with defaults.

## Addons: on by default, opt-in for the rest

PostgreSQL, Redis, and sendmail are configured automatically - most Django
projects need a database, a cache, and outgoing mail, so there is little
reason to ask for them explicitly. Drop `--no-redis` or `--no-sendmail` if
your project does not use one.

Celery and SSO touch your application code, not just the Cloudron config,
so they stay opt-in:

- `--celery` adds a worker and beat process, generates a `celery.py`
  module, wires it into your project's `__init__.py`, and adds
  `celery[redis]` to your requirements. It requires Redis, since Celery
  uses the Redis addon as its broker. {doc}`enable-celery` has more
  detail on the flag.
- `--sso` renders the Cloudron OIDC addon and a django-allauth provider
  configuration and adds the dependency, but you finish wiring allauth
  into `INSTALLED_APPS` and `urls.py` yourself - the success message after
  the deploy spells out the remaining steps. A project scaffolded with
  `dsd-cloudron new --sso` gets that wiring done automatically; retrofit
  cannot safely edit your existing URLconf and app list for you.
  {doc}`enable-sso` covers the rest of the setup.

## What gets written

Each deploy writes the Cloudron manifest, Dockerfile, `start.sh`,
supervisor configs, and nginx config, then appends a guarded settings
block that imports the Cloudron-specific Django settings. It also adds
the packages your configuration needs - `gunicorn` and `psycopg[binary]`
always, plus `django-redis`, `celery[redis]`, or `django-allauth` when
the matching flag is set. {doc}`/reference/generated-files` describes
each artifact in detail.

## Re-running the deploy

Re-running `manage.py deploy` is safe, but it is not silently idempotent.
The settings block is guarded against being added twice - if one is
already present, the command stops rather than appending a duplicate.
Rendered artifacts are skip-if-present: an existing `CloudronManifest.json`
or `Dockerfile` is left alone unless you pass `--force-overwrite`, which
regenerates them from your current flags.

## Other flags

`--app-id`
: Reverse-DNS app id, e.g. `com.example.blog`. Defaults to one derived
  from your project name.

`--memory-limit`
: Memory limit in bytes. Defaults to 1073741824 (about 1 GB).

`--health-check-path`
: Path Cloudron polls for a 2xx response. Defaults to `/`; point it at a
  route that returns one if your root view does not.

`--server`
: Which logged-in Cloudron server to target, if you are authenticated to
  more than one.

`--allow-selfsigned`
: Accept a self-signed certificate on that server.

`--force-overwrite`
: Regenerate artifacts that already exist.

See the CLI reference for the complete list with full descriptions.
