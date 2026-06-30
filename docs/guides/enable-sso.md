# Enable single sign-on

`--sso` lets your users sign in with their Cloudron account instead of a
Django password. This guide covers what the flag generates, what it leaves
for you to wire up on a retrofit, and how the login round-trip works.

## What `--sso` generates

Add the flag to either command:

```bash
python manage.py deploy --location blog --sso
dsd-cloudron new "My App" --sso
```

Either way, the deploy:

- Declares the Cloudron `oidc` addon in `CloudronManifest.json`, with
  `optionalSso: true` so the app still accepts the local admin account
  alongside Cloudron sign-in.
- Renders a `SOCIALACCOUNT_PROVIDERS` block in the generated Cloudron
  settings, pointed at the OIDC credentials Cloudron injects at runtime.
- Adds `django-allauth` to your requirements.

The login round-trip uses the redirect URI
`/accounts/oidc/cloudron/login/callback/` - this is the standard allauth
OIDC callback path, and it is what the `oidc` addon is configured to send
users back to after they authenticate with Cloudron.

## Retrofit: finish the allauth wiring

On an existing project, `manage.py deploy --sso` cannot safely rewrite your
`INSTALLED_APPS` or `urls.py` - it does not know what is already there, or
in what order. So a retrofit deploy renders the addon and the provider
config, then stops short of wiring allauth into your project. The deploy's
success message spells out the remaining steps:

- Add `django.contrib.sites`, `allauth`, `allauth.account`,
  `allauth.socialaccount`, and
  `allauth.socialaccount.providers.openid_connect` to `INSTALLED_APPS`.
- Set `SITE_ID`.
- Add `allauth.account.auth_backends.AuthenticationBackend` to
  `AUTHENTICATION_BACKENDS`, keeping
  `django.contrib.auth.backends.ModelBackend` alongside it.
- Add `allauth.account.middleware.AccountMiddleware` to `MIDDLEWARE`, after
  `django.contrib.auth.middleware.AuthenticationMiddleware`.
- Include `allauth.urls` in your URLconf.
- Run `python manage.py migrate` to create allauth's tables.

If you would rather not do this by hand, {doc}`scaffold-new-project` with
`--sso` wires all of it into the generated project automatically, since
there is no existing app list or URLconf to risk breaking.

## Signing in

Once allauth is wired in and the app is deployed, your Cloudron users sign
in through the normal Cloudron login flow and land back in the app
authenticated. The local `admin` account from first install does not go
away - it is your break-glass account. The first time you sign in with
Cloudron SSO, use that account (or `cloudron exec` into the container) to
promote your own Cloudron user to staff or superuser in the Django admin.

## Other flags

See {doc}`retrofit-existing-project` or {doc}`scaffold-new-project` for the
rest of the flags `--sso` is commonly combined with, including `--celery`.
