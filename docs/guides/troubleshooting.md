# Troubleshooting

Known failure modes, what causes each one, and how to fix it.

## Install fails its health check

**Symptom:** `cloudron install` or `cloudron update` fails while waiting
for the app to report healthy.

**Cause:** Cloudron polls `healthCheckPath` from `CloudronManifest.json`
after starting the container, and the install or update does not
complete until that path returns a 2xx response. If the path 404s,
redirects to a login page, or returns any other non-2xx status, the
health check never passes.

**Fix:** A project scaffolded with `dsd-cloudron new` ships a `/healthz/`
view that always returns 200, and `healthCheckPath` is set to `/healthz/`
by default, so this should not come up on a greenfield project. On a
retrofit, the default `healthCheckPath` is `/`, which only works if your
root URL returns 2xx without authentication. If it does not - for
example, if `/` redirects anonymous users to a login page - pass
`--health-check-path` pointed at a route that does, or add a dedicated
health-check view and point the flag at that instead:

```bash
python manage.py deploy --location blog --health-check-path /healthz/
```

## Install rejected for an empty author

**Symptom:** `cloudron install` rejects the build before it even starts,
complaining about the manifest's `author` field.

**Cause:** Cloudron requires `CloudronManifest.json` to declare a
non-empty `author`, and a manifest with an empty string fails server-side
validation.

**Fix:** This should not happen with dsd-cloudron - the packaging core
always writes a default `author` into the generated manifest, so a fresh
deploy is never affected. If you see this, check whether
`CloudronManifest.json` was hand-edited and the `author` field was
cleared or removed; restore a non-empty value and re-run `cloudron
install`.

## gunicorn logs a control-socket error on start

**Symptom:** The container starts, but the logs show gunicorn logging a
control-socket error early in the start sequence.

**Cause:** gunicorn's `user=cloudron` supervisor program ordinarily
inherits `HOME=/home/cloudron`, and tries to write a control socket
there. `/home/cloudron` is part of the read-only image layer, not the
writable `/app/data` volume, so the write fails.

**Fix:** The generated `supervisor/gunicorn.conf` already points `HOME`
at the writable `/tmp` instead of `/home/cloudron`, so this should not
occur with an unmodified deploy. If you have customized the supervisor
config, check that the `environment=` line on the `gunicorn` program
still sets `HOME=/tmp` (alongside `USER=cloudron`).

## Bare visit or post-login redirect returns 404

**Symptom:** Visiting the app's root URL, or the redirect Django sends a
user to after logging in, returns a 404 instead of a page.

**Cause:** A fresh Django project has no view registered at `/` by
default, so a request there falls through to Django's 404 handler -
which is also where `LOGIN_REDIRECT_URL` points unless you have changed
it.

**Fix:** Serve something at `/`. A project scaffolded with
`dsd-cloudron new` ships a landing-page view at `/` for exactly this
reason. On a retrofit, add a view (or redirect) at `/`, or change
`LOGIN_REDIRECT_URL` to point at wherever your app's real entry point
is.

## Still stuck

`cloudron logs --app <subdomain> -f` is the first thing to check for any
failure during or after install - see {doc}`operating-and-updating` for
the rest of the update and logging loop. `cloudron debug --app
<subdomain>` pauses the app and makes its filesystem temporarily
writable, which is useful for poking around inside a container that
will not start cleanly.
