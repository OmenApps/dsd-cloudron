"""User-facing messages for dsd-cloudron."""

from textwrap import dedent

confirm_automate_all = """
The --automate-all flag means the deploy command will:
- Configure your project for deployment to Cloudron.
- Commit all changes needed for deployment.
- Run `cloudron install` to build the image on your Cloudron server and install the app.
"""

cli_not_installed = """
The `cloudron` CLI does not appear to be installed.
Install it with:
    npm install -g cloudron
Then authenticate with:
    cloudron login my.example.com
"""

cli_logged_out = """
You do not appear to be logged in to a Cloudron server.
Authenticate with:
    cloudron login my.example.com
For a self-signed server, add --allow-selfsigned.
"""

cloudron_settings_found = """
A Cloudron settings block was already found in your settings file.
"""

cant_overwrite_settings = """
The deploy command will not overwrite the existing Cloudron settings block.
Remove the block manually, or re-run after reviewing it.
"""

location_required = """
--location is required with --automate-all so `cloudron install` knows which
subdomain to install to (otherwise it would prompt interactively).
Example: --location blog
"""

celery_requires_redis = """
--celery uses the Redis addon as its broker, but --no-redis was also passed.
Re-run without --no-redis, or drop --celery.
"""

install_failed = """
`cloudron install` did not finish successfully. The image may have built but
failed its health check, or the build itself failed. Check the output above and
`cloudron logs`. A common cause is healthCheckPath returning a non-2xx response
under DEBUG=False; re-run with --health-check-path pointing at a 2xx route.
"""


def health_check_path_unresolved(path):
    """Warning when the configured health check path does not resolve in the URLconf.

    Best-effort and emitted before `cloudron install`, so the user can fix a path
    that would 404 the install's health check instead of discovering it only after
    a full build cycle. A route reachable only through middleware can fail to
    resolve while still working, so this warns rather than blocks.
    """
    return (
        f"\nWarning: the configured health check path {path!r} does not resolve in "
        "your project's URLconf. Cloudron requires healthCheckPath to return a 2xx "
        "response or the install fails its health check. Re-run with "
        "--health-check-path pointing at a route that returns 200, or edit "
        "CloudronManifest.json. If the path is reachable only through middleware, "
        "you can ignore this.\n"
    )


def partial_write_failed(error):
    """Abort message when writing an artifact into the project fails midway.

    render_all is not transactional, so a filesystem error (permission denied,
    read-only path, disk full) can leave some files written and others not.
    """
    return (
        f"\nFailed while writing Cloudron files into your project: {error}\n"
        "Your project may be partially modified. Fix the cause (for example a "
        "permissions or disk-space problem) and re-run the deploy; pass "
        "--force-overwrite to regenerate files that were already written.\n"
    )


def reconfigure_overwrite_prompt(rel):
    """Per-file prompt for the retrofit reconfigure flow.

    The diff for `rel` has already been printed; this asks whether to replace the
    on-disk file with the freshly rendered version.
    """
    return f"Overwrite {rel} with the freshly rendered version?"


reconfigure_update_reminder = (
    "\nReconfigure complete. Run `cloudron update --app <subdomain>` to build and "
    "roll these changes out to the running app.\n"
)


def uv_requirements_exported(req_path):
    """Status note when a uv project's lock is materialized for core.

    Core detects only req_txt/poetry/pipenv. This runs in dsd_pre_inspect, before
    core's inspection, so a uv-only project is exported to a requirements.txt that
    core then reads as req_txt. Report it so the generated (and staged) file is not
    a surprise.
    """
    return (
        f"  Detected a uv project; exported your locked dependencies to "
        f"{req_path} so the deploy can proceed. It has been staged for you."
    )


def uv_export_failed(detail):
    """Abort message when exporting a uv project's lock fails.

    `uv export --frozen` fails if uv is missing or the lock is out of date. Name
    the likely remedy so the user can fix it and re-run rather than seeing a raw
    subprocess error.
    """
    return (
        f"\nCould not export your uv dependencies to a requirements file for the "
        f"Cloudron deploy:\n{detail}\n"
        "Make sure uv is installed and your lock is current (`uv lock`), then "
        "re-run the deploy.\n"
    )


def requirements_export_failed(manager, detail):
    """Abort message when exporting the locked requirements for the image fails.

    poetry 2.x ships `export` only via poetry-plugin-export, and `pipenv
    requirements` needs a recent pipenv. Name the remedy so the user can fix it and
    re-run rather than seeing a raw subprocess error.
    """
    remedy = (
        "add the export plugin with `poetry self add poetry-plugin-export`"
        if manager == "poetry"
        else "upgrade pipenv (`pipenv requirements` needs a recent version)"
    )
    return (
        f"\nCould not export your {manager} dependencies to a requirements file "
        f"for the Cloudron image build:\n{detail}\n"
        f"Fix it ({remedy}) and re-run the deploy.\n"
    )


def noninteractive_settings_conflict():
    """Abort message when an unattended re-deploy meets an existing settings block.

    Under --automate-all core cannot prompt for overwrite permission (its prompt
    reads stdin), so a prior Cloudron settings block would otherwise hang or crash
    the run. Tell the user the two ways forward.
    """
    return (
        "\nA Cloudron settings block already exists in your settings file, and "
        "--automate-all cannot prompt to overwrite it.\n"
        "Re-run interactively (without --automate-all) to be asked, or pass "
        "--force-overwrite to replace the existing block.\n"
    )


def unsafe_cli_value(flag, value):
    """Rejection message for a CLI value that is unsafe to interpolate.

    location and server are spliced into `cloudron` command strings, so an
    unexpected character (whitespace, a quote, a shell metacharacter) could
    mis-split the command or crash the argument parser. Restrict them to the
    characters real subdomains and hostnames use.
    """
    return (
        f"\nThe value for {flag} ({value!r}) contains characters that are not "
        "allowed. Use only letters, digits, dots, and hyphens.\n"
    )


def followup_notes(config):
    """Guidance for the app-intrusive toggles, appended to the success message.

    The infra addons (postgresql, redis, sendmail) are self-contained, so only
    the toggles that need code in the user's project are called out here.
    """
    notes = []
    if config.enable_celery:
        notes.append(
            "- Celery: a celery.py app module was generated in your project "
            "package and imported from its __init__.py. Define your tasks; the "
            "worker and beat processes start under supervisor on Cloudron."
        )
    if config.enable_sso:
        notes.append(
            "- SSO: the Cloudron oidc addon, a SOCIALACCOUNT_PROVIDERS block, and the "
            "account/social adapters were written. cloudron_adapters.py closes local "
            "self-service signup while keeping OIDC first-login provisioning, and "
            "cloudron_settings.py already points ACCOUNT_ADAPTER and SOCIALACCOUNT_ADAPTER "
            "at it on Cloudron (these, and the SOCIALACCOUNT_PROVIDERS block, override any "
            "allauth adapters or providers you already configured - but only on Cloudron). "
            "django-allauth[mfa,socialaccount] is installed, so MFA is available. "
            "django-allauth is not wired into your project yet - the plugin does not edit "
            "your settings.py or urls.py. Apply this block by hand, adjusting to your "
            "project: skip any entry you already have (a second django.contrib.sites, SITE_ID, "
            "or LOGIN_REDIRECT_URL would duplicate or override yours), and make sure TEMPLATES "
            "includes django.template.context_processors.request (a Django startproject "
            "default allauth needs; manage.py check flags it if absent). Then run "
            "`python manage.py migrate`:\n"
            "\n"
            "    # settings.py - add to INSTALLED_APPS:\n"
            '    "django.contrib.sites",\n'
            '    "allauth",\n'
            '    "allauth.account",\n'
            '    "allauth.socialaccount",\n'
            '    "allauth.socialaccount.providers.openid_connect",\n'
            '    "allauth.mfa",\n'
            "\n"
            "    # settings.py - add to MIDDLEWARE, after AuthenticationMiddleware:\n"
            '    "allauth.account.middleware.AccountMiddleware",\n'
            "\n"
            "    # settings.py - site id, auth backends, post-login landing:\n"
            "    SITE_ID = 1\n"
            "    AUTHENTICATION_BACKENDS = [\n"
            '        "django.contrib.auth.backends.ModelBackend",\n'
            '        "allauth.account.auth_backends.AuthenticationBackend",\n'
            "    ]\n"
            '    LOGIN_REDIRECT_URL = "/"  # allauth serves no /accounts/profile/ view\n'
            "\n"
            "    # urls.py - add include to your django.urls import, then to urlpatterns:\n"
            '    path("accounts/", include("allauth.urls")),'
        )
    return "\n\n".join(notes)


def changes_summary(config, added_requirements):
    """List the addons and requirements the deploy added, so a retrofit user
    sees exactly what changed in their project."""
    addons = ["postgresql", "localstorage"]
    if config.enable_redis:
        addons.append("redis")
    if config.enable_sendmail:
        addons.append("sendmail")
    if config.enable_sso:
        addons.append("oidc")
    lines = [
        "Changes made to your project:",
        f"- Cloudron addons declared in the manifest: {', '.join(addons)}.",
        "- Rendered the Cloudron artifact set (CloudronManifest.json, Dockerfile, "
        ".dockerignore, start.sh, nginx.conf, supervisor/, cloudron_settings.py, "
        "README-cloudron.md) and appended the settings import.",
        "- Wrote CLOUDRON_NEXT_STEPS.md next to your project - a copy of this "
        "summary and any follow-up notes you can keep after the output scrolls away.",
    ]
    if config.ships_retrofit_adapters:
        lines.append(
            "- Wrote cloudron_adapters.py into your project package (the allauth "
            "account and social adapters cloudron_settings.py points at)."
        )
    if added_requirements:
        lines.append(f"- Added requirements: {', '.join(added_requirements)}.")
    if config.pkg_manager in ("poetry", "pipenv"):
        lines.append(
            f"- Generated requirements.txt from your {config.pkg_manager} lock for "
            "the image build (the image installs from it with uv; it never runs "
            f"{config.pkg_manager}). If your dependencies changed recently, run "
            f"`{config.pkg_manager} lock` and redeploy so the export is current. "
            "Review requirements.txt before committing: it reflects your locked "
            "versions as-is (including security-sensitive pins like gunicorn, and "
            "any private index credentials your lock carries)."
        )
    return "\n".join(lines)


def success_msg(config, location, log_output=""):
    """Config-only success message (no --automate-all)."""
    location_hint = location or "<subdomain>"
    msg = dedent(f"""
        --- Your project is now configured for deployment to Cloudron ---

        To deploy:
            cloudron login my.example.com
            cloudron install -l {location_hint}

        For later deploys:
            cloudron update --app {location_hint}
            cloudron logs --app {location_hint} -f

        Note: healthCheckPath is "{config.health_check_path}". It must return a
        2xx response or the install fails its health check. If your project
        returns 404 there under DEBUG=False, re-run with --health-check-path
        pointing at a path that returns 200, or edit CloudronManifest.json.

        A default admin account `admin` is created on the first install. Its
        password is generated per install and saved on the server at
        /app/data/.initial_admin_password. Retrieve it with:
            cloudron exec --app {location_hint} -- cat /app/data/.initial_admin_password
        Read it during this first-boot window: the file is removed automatically on
        the next start once the app is initialized. If you miss it, reset with
        `manage.py changepassword admin` via `cloudron exec`. Sign in at /admin/
        and change the password.
        """)
    if log_output:
        msg += (
            "\n- You can find a full record of this configuration in the "
            "dsd_logs directory.\n"
        )
    return msg


def success_msg_automate_all(deployed_url):
    """Success message after an automated `cloudron install`.

    deployed_url is empty when the URL is not scraped from the build output (the
    default), so fall back to telling the user how to find the running app.
    """
    where = deployed_url or "(run `cloudron list` or open your Cloudron dashboard)"
    return dedent(f"""
        --- Your project has been deployed to Cloudron ---

        It should be available at:
            {where}

        A default admin account `admin` was created; its password is generated
        per install and saved on the server at /app/data/.initial_admin_password.
        Read it with `cloudron exec --app <subdomain> -- cat
        /app/data/.initial_admin_password` during this first-boot window: the file
        is removed automatically on the next start once the app is initialized. If
        you miss it, reset with `manage.py changepassword admin` via `cloudron
        exec`. Change the password after signing in.
        """)
