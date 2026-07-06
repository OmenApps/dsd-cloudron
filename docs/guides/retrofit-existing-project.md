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
  configuration, adds the dependency, and ships a `cloudron_adapters.py` that
  closes local self-service signup - with `ACCOUNT_ADAPTER` and
  `SOCIALACCOUNT_ADAPTER` already pointed at it on Cloudron. You finish wiring
  allauth into `INSTALLED_APPS`, `MIDDLEWARE`, and `urls.py` yourself; the
  success message and `CLOUDRON_NEXT_STEPS.md` spell out the exact block. A
  project scaffolded with `dsd-cloudron new --sso` gets that wiring done
  automatically, since retrofit cannot safely edit your existing URLconf and
  app list for you. {doc}`enable-sso` covers the rest of the setup.

## What gets written

Each deploy writes the Cloudron manifest, Dockerfile, `start.sh`,
supervisor configs, and nginx config, then appends a guarded settings
block that imports the Cloudron-specific Django settings. It also adds
the packages your configuration needs: `gunicorn` and `psycopg[binary]`
(the driver is skipped if your project already depends on a Postgres
driver - `psycopg`, `psycopg2`, or `psycopg2-binary`), plus `django-redis`,
`celery[redis]`, or `django-allauth[mfa,socialaccount]` when the matching
flag is set. A package your project already pins is never added twice.
{doc}`/reference/generated-files` describes each artifact in detail.

## Dependency managers

`dsd-cloudron` works whether your project pins dependencies with a
`requirements.txt`, Poetry, Pipenv, or [uv](https://docs.astral.sh/uv/):

- With a `requirements.txt`, the deploy appends the packages above to it
  directly.
- With Poetry or Pipenv, the deploy exports your locked dependencies to a
  `requirements.txt` for the Cloudron image, so those tools never run inside
  the build.
- With uv - a `uv.lock` and no `requirements.txt` - the deploy exports your
  lock to a `requirements.txt` up front and stages it for you, then follows
  the same path. The export runs `uv export --frozen`, so your lock must be
  current; run `uv lock` first if the deploy reports it is out of date.

In every case the Cloudron image installs the resulting `requirements.txt`
with uv.

## Re-running the deploy

Re-running `manage.py deploy` is safe, but it is not silently idempotent.
How an existing settings block is handled depends on how you re-run:

- Interactively (no flags), the command asks before replacing the block, so
  a re-run cannot append a duplicate.
- With `--force-overwrite`, the existing block is stripped and replaced
  without prompting, so you still end up with exactly one block.
- With `--automate-all` and no `--force-overwrite`, the command cannot
  prompt, so it aborts cleanly and tells you to re-run interactively or pass
  `--force-overwrite` rather than hanging.

Rendered artifacts are skip-if-present: an existing `CloudronManifest.json`
or `Dockerfile` is left alone unless you pass `--force-overwrite`, which
regenerates them from your current flags. For a reviewable middle ground -
re-render the deployed configuration with a diff and a prompt per file instead
of the blunt clobber - pass `--reconfigure` (with the same stack toggles you
deployed with); see {doc}`operating-and-updating`.

## Other flags

`--app-id`
: Reverse-DNS app id, e.g. `com.example.blog`. Defaults to one derived
  from your project name.

`--memory-limit`
: Memory limit in bytes. Defaults to 1073741824 (about 1 GB), or about 1.5 GB
  with `--wagtail`. An explicit value always wins.

`--health-check-path`
: Path Cloudron polls for a 2xx response. Defaults to `/`; point it at a
  route that returns one if your root view does not.

`--server`
: Which logged-in Cloudron server to target, if you are authenticated to
  more than one.

`--allow-selfsigned`
: Accept a self-signed certificate on that server.

`--force-overwrite`
: Regenerate artifacts that already exist, and replace an existing Cloudron
  settings block without prompting.

`--reconfigure`
: Re-render the artifacts of the configuration you already deployed, with a
  diff and a prompt before overwriting each file, instead of skip-if-present or
  `--force-overwrite`. Pass the same stack toggles you deployed with. See
  {doc}`operating-and-updating`.

`--wagtail`
: Configure an existing Wagtail project for Cloudron - sets
  `WAGTAILADMIN_BASE_URL`, forces the database search backend, and raises the
  default memory limit. See {doc}`deploy-wagtail-project`.

See the CLI reference for the complete list with full descriptions.
