# Architecture

This page explains how dsd-cloudron is put together and why the generated
artifacts look the way they do. Read it if you want to understand the
deployment rather than just operate it - the guides and
{doc}`/reference/generated-files` cover the day-to-day mechanics.

## One packaging core, two entry points

dsd-cloudron serves two audiences from a single codebase. `python manage.py
deploy` retrofits an existing Django project, and `dsd-cloudron new`
scaffolds a brand new one. Both call the same packaging core, so a retrofit
and a fresh scaffold end up with the same artifact set: `CloudronManifest.json`,
`Dockerfile`, `start.sh`, `nginx.conf`, the `supervisor/` configs, and the
`cloudron_settings.py` glue. The two entry points differ in how much of the
surrounding project already exists, not in what gets rendered.

This matters in practice: a guide written for the retrofit path and one
written for the greenfield path are describing the same generated files,
just arrived at from different starting points. See
{doc}`/guides/retrofit-existing-project` and {doc}`/guides/scaffold-new-project`.

## The readonly filesystem

A Cloudron container's filesystem is readonly at runtime, with three
exceptions: `/tmp`, `/run`, and `/app/data`. Of those three, only `/app/data`
is a persistent, backed-up volume - `/tmp` and `/run` are wiped on every
restart.

dsd-cloudron's generated files follow that split:

- Runtime configuration that needs to exist while the container is up, but
  doesn't need to survive a restart, goes in `/run` (the gunicorn socket,
  static files collected at start, and similar).
- Anything that must survive an update or a container rebuild goes in
  `/app/data`: uploaded media, the persistent `SECRET_KEY`, and the marker
  files described below. (The PostgreSQL and Redis addons keep their own
  storage outside the app container, so they aren't part of this split.)

Writing persistent state anywhere else is a bug: the next `cloudron update`
rebuilds the container from the image and silently discards it.

## TLS termination and httpPort

The app itself speaks plain HTTP on the port named by `httpPort` in
`CloudronManifest.json`. Cloudron's platform proxy sits in front of every
app, terminates TLS, and forwards plain HTTP traffic to that port - the app
never sees a certificate and doesn't need to manage one. This is also why
`CSRF_TRUSTED_ORIGINS` and the proxy-related settings in
`cloudron_settings.py` exist: from Django's point of view, every request
arrives over HTTP from the local proxy, and the `X-Forwarded-*` headers are
what tell it the original request was HTTPS.

## Migrations and one-time setup

`manage.py migrate` runs on every container start, not just the first one.
There's no separate "first boot" code path for schema changes - an update
that ships a new migration applies it automatically the next time the
container comes up.

True one-time setup - generating a `SECRET_KEY`, creating the local `admin`
superuser - is guarded by marker files under `/app/data` instead, since that's
the one place state survives a rebuild. `start.sh` checks for
`/app/data/.secret_key` and `/app/data/.initialized` before doing that work,
so it runs exactly once even though the rest of the container is rebuilt
from scratch on every update. See {doc}`/guides/operating-and-updating` for
what that looks like across an update cycle.

## Privilege model

`start.sh` runs as root - that's required to create the runtime directories
and fix ownership before anything else starts. Each start, it `chown`s
`/app/data` and the run directories to `cloudron:cloudron`, then uses `gosu
cloudron:cloudron` for the one-off setup commands: collecting static files,
running `migrate`, and (on first boot only) creating the superuser.

It does not, however, hand the long-running process over to `gosu`. `start.sh`
finishes by `exec`-ing `supervisord` directly, as root, so supervisord
becomes the container's main process and is the one that receives `SIGTERM`
when Cloudron stops or restarts the app. The actual long-running work still
runs unprivileged: gunicorn and, when `--celery` is set, the Celery worker
and beat processes each set `user=cloudron` in their supervisor program
stanza, and nginx drops its worker processes to `cloudron` through the `user
cloudron;` directive in `nginx.conf` (its master process stays root, which
is normal nginx behavior). Root shows up only in the boot sequence and as
supervisord's PID 1 - nothing that handles an actual request runs as root.

## The base image

Whatever a project's `Dockerfile` does in earlier build stages - installing
dependencies, compiling assets - the final stage must be `FROM
cloudron/base:5.0.0`, pinned by digest. That's the image Cloudron's platform
expects: it provides the `cloudron` and `gosu` users/tooling that `start.sh`
relies on, and Cloudron validates against it at install time. Earlier stages
can use any base that's convenient for the build.
