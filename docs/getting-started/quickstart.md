# Quickstart

This walks through the fastest path to a running app: scaffolding a brand
new Django project and installing it on a Cloudron server. It assumes you
have already completed the steps in {doc}`installation`.

## Scaffold a new project

```bash
dsd-cloudron new "My App"
cd my_app
```

This generates a Django project along with the full Cloudron artifact set:
`CloudronManifest.json`, `Dockerfile`, `start.sh`, supervisor configs, nginx
config, and the settings glue connecting them.

## Install it on your server

```bash
cloudron install -l my-app
```

`cloudron` builds the image and installs the app at the `my-app` subdomain
on the server you logged into during installation.

## First sign-in

The first install creates a local `admin` account and saves its generated
password on the server, at `/app/data/.initial_admin_password`. Read it
with:

```bash
cloudron exec --app my-app -- cat /app/data/.initial_admin_password
```

Read it during the first-boot window: the file is removed automatically on
the next start once the app is initialized, so it does not linger in every
backup. If you miss it, reset with `manage.py changepassword admin` via
`cloudron exec`. Sign in at `/admin/` with that password and change it.

## Next steps

If you have an existing Django project rather than a fresh one,
{doc}`/guides/retrofit-existing-project` covers configuring it with
`manage.py deploy` instead of `dsd-cloudron new`. Want users to sign in
with their Cloudron account instead of a local password? See
{doc}`/guides/enable-sso`. For updates, logs, and what actually persists
between deploys, see {doc}`/guides/operating-and-updating`.
