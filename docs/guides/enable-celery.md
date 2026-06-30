# Enable Celery

`--celery` adds a Celery worker and beat process to your deployment, for
background tasks and scheduled jobs. This guide covers what the flag
generates and the one hard requirement it has on Redis.

## What `--celery` generates

Add the flag to either command:

```bash
python manage.py deploy --location blog --celery
dsd-cloudron new "My App" --celery
```

Either way, the deploy:

- Generates a `<project>/celery.py` module and wires it into your
  project's `__init__.py` by importing `celery_app` from it, so
  `celery -A <project>` finds the app automatically.
- Adds `celery-worker` and `celery-beat` supervisor programs, run alongside
  gunicorn on the same Cloudron instance.
- Adds `celery[redis]` to your requirements.

Unlike `--sso`, the `__init__.py` wiring happens on a retrofit too - there
is nothing project-specific to risk breaking by adding one import line, so
both `manage.py deploy --celery` and `dsd-cloudron new --celery` leave you
with a working Celery app. From there, define your tasks in your own apps;
the worker picks them up through `app.autodiscover_tasks()`.

## Redis is the broker

The worker and beat both connect to the Cloudron Redis addon as their
broker, using the same `CLOUDRON_REDIS_URL` the rest of the app reads.
There is no separate message broker to configure.

Because of that, Redis cannot be turned off when Celery is on. Pairing
`--celery` with `--no-redis` is rejected before anything is written, no
matter which entry point you use: both `manage.py deploy` and
`dsd-cloudron new` refuse the combination, with an error pointing out
that Celery needs the Redis addon as its broker and telling you to drop
one of the two flags. The exact wording differs between the two
commands, but the rule is the same either way.

Redis is enabled by default, so in practice this only comes up if you
explicitly pass both flags together.

## What persists

The beat schedule file lives at `/app/data/celerybeat-schedule`, inside
the persistent, backed-up storage volume - so scheduled jobs keep their
timing across `cloudron update` and container restarts rather than
re-triggering from a blank schedule on every redeploy.

## Combining with SSO

`--celery` and {doc}`enable-sso` are independent - nothing about one
affects the other, and both can be passed together:

```bash
dsd-cloudron new "My App" --celery --sso
```

See {doc}`retrofit-existing-project` or {doc}`scaffold-new-project` for
the full flag list.
