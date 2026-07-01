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
            "- SSO: the Cloudron oidc addon and a SOCIALACCOUNT_PROVIDERS block "
            "were written, but django-allauth is not wired into your project yet. "
            "Add django.contrib.sites, allauth, allauth.account, "
            "allauth.socialaccount, and "
            "allauth.socialaccount.providers.openid_connect to INSTALLED_APPS; set "
            "SITE_ID; set AUTHENTICATION_BACKENDS to keep "
            "django.contrib.auth.backends.ModelBackend and add "
            "allauth.account.auth_backends.AuthenticationBackend; add "
            "allauth.account.middleware.AccountMiddleware to MIDDLEWARE after "
            "django.contrib.auth.middleware.AuthenticationMiddleware; include "
            "allauth.urls; and run migrate. Automated SSO wiring is planned for a "
            "later release."
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
        "README-cloudron.md; see the per-file lines above for written vs skipped) "
        "and appended the settings import.",
    ]
    if added_requirements:
        lines.append(f"- Added requirements: {', '.join(added_requirements)}.")
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
        Sign in at /admin/, change the password, then delete that file.
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
        /app/data/.initial_admin_password`, change it immediately, then delete
        that file.
        """)
