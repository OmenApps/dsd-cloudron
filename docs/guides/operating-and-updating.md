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

## Reconfigure after the first deploy

The generated files are the control surface, but re-running the deploy is blunt:
rendered artifacts are skip-if-present by default, and `--force-overwrite` clobbers
every artifact including ones you hand-edited. Reconfigure is the reviewable middle
ground for re-rendering the artifacts of the configuration you already deployed - to
pick up an improved template or restore a file you hand-edited by mistake - and for
adjusting the manifest's sizing.

- Retrofit: `python manage.py deploy --reconfigure` (pass the same toggles you
  deployed with, for example `--sso`, so the re-render matches).
- Greenfield: `dsd-cloudron reconfigure` inside the project (add `--memory-limit` or
  `--health-check-path` to change a manifest value).

For each artifact it would write, reconfigure shows a diff against the file on disk
and asks before overwriting; an unchanged file is skipped without a prompt, and a
file you decline is left exactly as it is. In the manifest it touches only `memoryLimit`
and `healthCheckPath`, and it preserves whatever is deployed unless you change it:
greenfield takes a new value from `--memory-limit`/`--health-check-path`, while the
retrofit path always preserves the deployed sizing (change it by editing
`CloudronManifest.json` - the control surface - or re-deploying). Every other key, the
addon set, and any hand edit in `CloudronManifest.json` are preserved. Reconfigure never
edits your `settings.py`.

Reconfigure does not change *which stacks are enabled*. It re-renders artifacts but
never installs dependencies, wires apps, or adds and removes supervisor programs, so
enabling or disabling Celery, SSO, Redis, or sendmail through it would ship a broken
image (a dependency is missing) or a crash-looping one (a stale supervisor program the
platform still runs). If the toggles you pass (retrofit) or the project on disk
(greenfield) declare a different stack set than what is deployed, reconfigure refuses
and names the mismatch. To change a stack, re-run a full `deploy` (retrofit) or
re-scaffold with `dsd-cloudron new` (greenfield). Follow any change with `cloudron update`.

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
redeploying, drop a `/app/data/custom_settings.py` file on the server.
The generated `cloudron_settings.py` executes it last, so anything it sets -
`DATABASES`, `EMAIL_BACKEND`, a feature flag your project reads from settings -
overrides what dsd-cloudron generated.

For safety it runs the file **only** when it is owned by `root` and not
group- or other-writable, so a file the app process could write itself is
skipped (with a note on stderr). The app runs as `cloudron`, which cannot
`chown` a file to root, so create the override inside a root `cloudron exec`
shell:

```bash
cloudron exec --app <subdomain>
# in the shell (running as root):
cat > /app/data/custom_settings.py <<'EOF'
# your overrides here
EOF
chown root:cloudron /app/data/custom_settings.py
chmod 640 /app/data/custom_settings.py
```

Root ownership satisfies the gate; group `cloudron` mode 640 lets gunicorn
read it. It only takes effect on the next container start, so follow it with
`cloudron update` or a restart.

An override created with the old `cloudron push` recipe is `cloudron`-owned,
not root-owned, so it is now skipped. The same applies to a file whose owner
came back non-root after a backup restore or an app clone. Verify with
`cloudron exec --app <subdomain> -- ls -l /app/data/custom_settings.py` and
re-apply the `chown root:cloudron` + `chmod 640` above if it is not
`root:cloudron`.

## First sign-in

The first install creates a local `admin` account and saves its
generated password on the server, at `/app/data/.initial_admin_password`.
Read it with:

```bash
cloudron exec --app <subdomain> -- cat /app/data/.initial_admin_password
```

Read it during the first-boot window: the file is removed automatically on
the next start once the app is initialized, so it does not linger in every
backup. If you miss it, reset the password instead:

```bash
cloudron exec --app <subdomain> -- python3 /app/code/manage.py changepassword admin
```

Sign in at `/admin/` and change the password.

If the app was deployed with `--sso`, your day-to-day sign-in goes
through Cloudron instead; the local `admin` account remains as a
break-glass login. See {doc}`enable-sso` for the rest of that setup.
