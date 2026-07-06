# CLI reference

dsd-cloudron extends `python manage.py deploy` (the core django-simple-deploy
command, with an added dsd-cloudron options group) and ships the `dsd-cloudron`
console script, which has two subcommands: `new` (a standalone scaffolder with
its own parser) and `reconfigure` (re-render an existing scaffold's artifacts).
Each surface's flags are below.

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
: Memory limit in bytes. Default `1073741824` (about 1 GB), or
  `1610612736` (about 1.5 GB) when `--wagtail` is passed. An explicit value
  always wins over either default.

`--health-check-path`
: Path that returns a 2xx response when the app is healthy. Default `/`.

`--force-overwrite`
: Regenerate Cloudron artifacts that already exist, and replace an existing
  Cloudron settings block without prompting.

`--reconfigure`
: Re-render the artifacts of the configuration you already deployed, showing a
  diff and asking before overwriting each file - the reviewable middle ground
  between skip-if-present and the blunt `--force-overwrite`. Pass the same stack
  toggles you deployed with (for example `--sso`); reconfigure refuses if they
  name a different stack than what is deployed, and it preserves the deployed
  `memoryLimit`/`healthCheckPath`. See {doc}`/guides/operating-and-updating`.

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

`--wagtail`
: Configure an existing Wagtail project for Cloudron: set
  `WAGTAILADMIN_BASE_URL` and force the database search backend in
  `cloudron_settings.py`, and raise the default memory limit to about 1.5 GB.
  The health check stays `/` (a stock Wagtail site answers there); the i18n
  health view and multilingual wiring remain yours to add. See
  {doc}`/guides/deploy-wagtail-project`.

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
: Add the Cloudron OIDC addon and django-allauth. A scaffolded project is
  fully wired (`INSTALLED_APPS`, middleware, `urls.py`, with local self-service
  signup closed); a retrofit renders the addon and provider config but leaves
  the allauth wiring to you. See {doc}`/guides/enable-sso`.

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

## `dsd-cloudron reconfigure`

```bash
dsd-cloudron reconfigure [options]
```

Re-render a scaffolded project's Cloudron artifacts in place - to pick up an
improved template or restore a file you hand-edited by mistake - without
re-scaffolding. It shows a diff and asks before overwriting each artifact,
skips unchanged files, and leaves a declined file untouched. It never installs
dependencies or adds and removes supervisor programs, so it refuses if the
project on disk declares a different stack than the manifest already deploys.
See {doc}`/guides/operating-and-updating`.

`--project-dir`
: The scaffolded project to reconfigure. Default `.`.

`--memory-limit`
: New `memoryLimit` in bytes for `CloudronManifest.json`. Omitted, the current
  value is kept.

`--health-check-path`
: New `healthCheckPath` for `CloudronManifest.json`. Omitted, the current value
  is kept.
