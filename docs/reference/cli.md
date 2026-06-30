# CLI reference

dsd-cloudron adds flags to two entry points: `python manage.py deploy` (the
core django-simple-deploy command, extended with a dsd-cloudron options
group) and `dsd-cloudron new` (a standalone scaffolder with its own
parser).

## `python manage.py deploy`

`--automate-all` is a django-simple-deploy core flag, not one dsd-cloudron
adds. Without it, the deploy only writes Cloudron config files; with it,
the same command also commits the changes and runs the Cloudron build and
install. See {doc}`/guides/retrofit-existing-project` for how that plays
out.

The flags below belong to dsd-cloudron, under the "Options for
dsd-cloudron" argument group:

`--location`
: Cloudron subdomain to install to, e.g. `blog`.

`--app-id`
: Reverse-DNS app id, e.g. `com.example.blog`.

`--memory-limit`
: Memory limit in bytes. Default `1073741824` (about 1 GB).

`--health-check-path`
: Path that returns a 2xx response when the app is healthy. Default `/`.

`--force-overwrite`
: Regenerate Cloudron artifacts that already exist.

`--server`
: Cloudron server domain, e.g. `my.example.com`. Selects which logged-in
  session the deploy uses.

`--allow-selfsigned`
: Allow a self-signed Cloudron server certificate.

`--no-redis`
: Do not configure the Redis addon.

`--no-sendmail`
: Do not configure the sendmail addon.

`--celery`
: Add a Celery worker and beat process, generate `<project>/celery.py`,
  and add celery to requirements. Celery's broker is the Redis addon, so
  pairing `--celery` with `--no-redis` is rejected before anything is
  written. See {doc}`/guides/enable-celery`.

`--sso`
: Render Cloudron OIDC config (the oidc addon and allauth provider
  settings) and add django-allauth. See {doc}`/guides/enable-sso`.

## `dsd-cloudron new`

```bash
dsd-cloudron new "<name>" [options]
```

`project_name`
: Positional. Human project name, e.g. `My Shop`.

`--output-dir`
: Where to create the project. Default `.`.

Infra addons are on by default; pass the matching `--no-` flag to turn one
off:

`--no-redis`
: Skip the Redis addon and cache configuration.

`--no-sendmail`
: Skip the sendmail addon.

App-stack toggles default off:

`--celery`
: Add a Celery worker and beat process, with `celery.py` generated and
  already wired into the project's `__init__.py`. See
  {doc}`/guides/enable-celery`.

`--sso`
: Add the Cloudron OIDC addon and django-allauth, fully wired into
  `INSTALLED_APPS`, middleware, and `urls.py`. See
  {doc}`/guides/enable-sso`.

`--ninja`
: Add a django-ninja API app mounted at `/api/`.

`--htmx`
: Add django-htmx, django-crispy-forms, and the Bootstrap 5 crispy
  template pack.

`--s3`
: Add django-storages and an S3-compatible media backend.

`--celery` requires Redis, so combining it with `--no-redis` is rejected
before anything is written. See {doc}`/guides/scaffold-new-project` for
what each toggle wires into the generated project.
