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

- Declares the Cloudron `oidc` addon in `CloudronManifest.json`.
- Renders a `SOCIALACCOUNT_PROVIDERS` block in the generated Cloudron
  settings, pointed at the OIDC credentials Cloudron injects at runtime.
- Adds `django-allauth[mfa,socialaccount]` to your requirements. The
  `socialaccount` extra pulls the OIDC runtime dependencies the generated
  provider imports so the app boots; the `mfa` extra adds allauth's
  multi-factor support. Retrofit and greenfield install the same extras.

Every generated manifest sets `optionalSso: true`, whether or not you
pass `--sso`. That setting only tells Cloudron the app will accept
sign-in without requiring it - on its own it does nothing, since there's
no `oidc` addon for Cloudron to offer unless `--sso` added one. The
addon and the allauth provider config are what `--sso` actually
contributes, and together they're what make Cloudron sign-in work
alongside the local admin account.

The login round-trip uses the redirect URI
`/accounts/oidc/cloudron/login/callback/` - this is the standard allauth
OIDC callback path, and it is what the `oidc` addon is configured to send
users back to after they authenticate with Cloudron.

## Retrofit: finish the allauth wiring

On an existing project, `manage.py deploy --sso` cannot safely rewrite your
`INSTALLED_APPS` or `urls.py` - it does not know what is already there, or in
what order. So a retrofit deploy does everything it safely can and leaves the
app-list and URLconf edits to you.

What the retrofit deploy does for you:

- Renders the `SOCIALACCOUNT_PROVIDERS` block in `cloudron_settings.py`.
- Ships `cloudron_adapters.py` into your project package - an account adapter
  that closes local self-service signup and a social adapter that keeps OIDC
  first-login provisioning working.
- Points `ACCOUNT_ADAPTER` and `SOCIALACCOUNT_ADAPTER` at that module from
  `cloudron_settings.py`, inside the `CLOUDRON_APP_ORIGIN` gate, so the wiring
  is active on Cloudron and inert in local development. You do not hand-author
  an adapter.

What you finish by hand - the deploy writes the exact block into
`CLOUDRON_NEXT_STEPS.md` next to your project:

- Add `django.contrib.sites`, `allauth`, `allauth.account`,
  `allauth.socialaccount`, `allauth.socialaccount.providers.openid_connect`,
  and `allauth.mfa` to `INSTALLED_APPS`.
- Set `SITE_ID`.
- Add `allauth.account.auth_backends.AuthenticationBackend` to
  `AUTHENTICATION_BACKENDS`, keeping
  `django.contrib.auth.backends.ModelBackend` alongside it.
- Add `allauth.account.middleware.AccountMiddleware` to `MIDDLEWARE`, after
  `django.contrib.auth.middleware.AuthenticationMiddleware`.
- Set `LOGIN_REDIRECT_URL` - allauth serves no `/accounts/profile/` view, so
  Django's default post-login redirect would 404.
- Include `allauth.urls` in your URLconf.
- Run `python manage.py migrate` to create allauth's tables.

Because the shipped adapters already point `ACCOUNT_ADAPTER` at an
`is_open_for_signup` that returns `False`, `/accounts/signup/` is closed for you
once you mount `allauth.urls` - you do not add that step yourself.

If you would rather not touch your app list and URLconf at all,
{doc}`scaffold-new-project` with `--sso` wires `INSTALLED_APPS`, `MIDDLEWARE`,
and the URLconf into the generated project automatically, since there is no
existing configuration to risk breaking.

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
