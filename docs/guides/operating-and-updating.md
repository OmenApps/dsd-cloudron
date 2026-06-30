# Operate and update a deployed app

Once an app is installed, day-to-day work is editing code or config and
pushing a new build - there is no separate "redeploy" command to learn.
This guide covers that loop, what survives it, and how to override
settings on the server without a code change.

## The update loop

```bash
# edit code or config, then:
cloudron update --app <subdomain>
cloudron logs --app <subdomain> -f
```

`cloudron update` rebuilds the image from your project and replaces the
running container; `cloudron logs -f` tails the new container's output so
you can confirm the start sequence - migrations, then supervisor bringing
up gunicorn and any other configured programs - completed cleanly.
`<subdomain>` is the same value you passed to `--location` (retrofit) or
to `cloudron install -l` (greenfield).

If you are iterating on the generated Cloudron artifacts themselves
rather than your application code, re-run `manage.py deploy` first to
regenerate them (add `--force-overwrite` to replace files that already
exist), then `cloudron update` to rebuild.

## What persists across updates

`/app/data` is the one writable, backed-up volume in the container; every
other path is rebuilt from the image on each update. Two things rely on
that:

- The PostgreSQL and Redis addons persist independently of the app
  container, so an update does not touch your data or cache.
- `manage.py migrate` runs on every start, not just the first one, so
  schema changes in a new build apply automatically when the updated
  container comes up.

First boot also does two pieces of one-time setup, each guarded so it
only runs once: it generates a `SECRET_KEY` and writes it to
`/app/data/.secret_key`, and it creates a local `admin` superuser. The
superuser step is gated on `/app/data/.initialized` - once that marker
file exists, later starts (including every `cloudron update`) skip
superuser creation, even after the rest of the container has been
rebuilt from scratch.

## Ad-hoc overrides

For a setting you want to change on the server without editing code and
redeploying, drop a `/app/data/custom_settings.py` file on the server:

```bash
cloudron push --app <subdomain> custom_settings.py /app/data/custom_settings.py
```

The generated `cloudron_settings.py` checks for that file last and
executes it in place if present, so anything it sets - `DATABASES`,
`EMAIL_BACKEND`, a feature flag your project reads from settings -
overrides what dsd-cloudron generated. It only takes effect on the next
container start, so follow it with `cloudron update` or a restart.

## First sign-in

The first install creates a local `admin` account and saves its
generated password on the server, at `/app/data/.initial_admin_password`.
Read it with:

```bash
cloudron exec --app <subdomain> -- cat /app/data/.initial_admin_password
```

Sign in at `/admin/` with that password and change it, then delete the
file - it stays in backups until you do:

```bash
cloudron exec --app <subdomain> -- rm /app/data/.initial_admin_password
```

If the app was deployed with `--sso`, your day-to-day sign-in goes
through Cloudron instead; the local `admin` account remains as a
break-glass login. See {doc}`enable-sso` for the rest of that setup.
