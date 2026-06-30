# dsd-cloudron

A [django-simple-deploy](https://django-simple-deploy.readthedocs.io) plugin that
configures and deploys Django projects to [Cloudron](https://cloudron.io). One
install serves two audiences:

- **Retrofit** an existing project: `python manage.py deploy --location <subdomain>`
- **Greenfield** a new project: `dsd-cloudron new "My App"`

Both render the same Cloudron artifact set (manifest, Dockerfile, start.sh,
supervisor configs, nginx, settings glue) through one packaging core.

## Install

```bash
pip install dsd-cloudron
npm install -g cloudron
cloudron login my.example.com
```

## Retrofit an existing Django project

```bash
pip install django-simple-deploy dsd-cloudron
python manage.py deploy --location blog          # config only
python manage.py deploy --location blog --automate-all   # config + install
```

Infra addons (PostgreSQL, Redis, sendmail) are on by default. The app-intrusive
ones are opt-in: `--celery` generates a Celery app module wired to the Redis
broker; `--sso` renders the Cloudron OIDC addon and a django-allauth provider
config and adds the dependency, then prints the steps to finish wiring allauth
into `INSTALLED_APPS`/`urls.py` and run `migrate` (a project scaffolded with
`dsd-cloudron new --sso` gets that wiring automatically). Useful flags:
`--health-check-path`, `--memory-limit`, `--app-id`, `--force-overwrite`,
`--no-redis`, `--no-sendmail`.

## Scaffold a new project

```bash
dsd-cloudron new "My App" --celery --sso
cd my_app
cloudron install -l my-app
```

## The control surface

The generated files ARE the configuration. Edit and re-deploy:

- `CloudronManifest.json` - addons, `memoryLimit`, `httpPort`, `healthCheckPath`.
  `healthCheckPath` must return a 2xx response or the install fails its health
  check. Greenfield ships a `/healthz/` view that returns 200.
- `<project>/cloudron_settings.py` - the Django glue, gated on
  `CLOUDRON_APP_ORIGIN` so it is inert during local development. Drop a
  `/app/data/custom_settings.py` on the server for ad-hoc overrides.
- `Dockerfile`, `start.sh`, `nginx.conf`, `supervisor/` - the runtime.

Re-running `manage.py deploy` is safe but not silently idempotent: the settings
block is guarded, and rendered artifacts are skip-if-present (regenerate with
`--force-overwrite`).

## Iterate

```bash
# edit code or config, then:
cloudron update --app <subdomain>
cloudron logs --app <subdomain> -f
```

`/app/data` and the Postgres/Redis addons persist across updates; `migrate` runs
on every start.

## First sign-in

A local `admin` account is created on the first install; its generated password
is saved on the server at `/app/data/.initial_admin_password`. Read it with
`cloudron exec --app <subdomain> -- cat /app/data/.initial_admin_password`, sign
in at `/admin/`, and change it - then delete that file (it persists in backups
until you do). With `--sso`, sign in with your Cloudron account; the local
`admin` is a break-glass account for promoting your user.

## License

MIT. See LICENSE.
