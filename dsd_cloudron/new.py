"""Greenfield scaffolder: `dsd-cloudron new <name>`.

Renders a Cloudron-ready Django project from the bundled cookiecutter template,
then renders the deploy artifacts through the shared packaging core.
"""

import argparse
import json
import keyword
import re
import sys
from pathlib import Path

from cookiecutter.exceptions import OutputDirExistsException
from cookiecutter.main import cookiecutter

from .packaging import CloudronAppConfig, ReconfigureError, reconfigure, render_all

TEMPLATE_DIR = Path(__file__).parent / "project_template"

# (flag dest, cookiecutter key, default "yes"/"no").
# Infra addons default on; app-stack toggles default off to stay lean.
_TOGGLES = [
    ("redis", "use_redis", "yes"),
    ("sendmail", "use_sendmail", "yes"),
    ("celery", "use_celery", "no"),
    ("sso", "use_sso", "no"),
    ("ninja", "use_ninja", "no"),
    ("htmx", "use_htmx", "no"),
    ("s3", "use_s3", "no"),
]


def _slugify(name):
    slug = name.strip().lower()
    slug = re.sub(r"[ \-.]+", "_", slug)
    return re.sub(r"[^a-z0-9_]", "", slug)


def _fail(message):
    """Abort with a clean message *before* any project files are written."""
    print(f"dsd-cloudron: error: {message}", file=sys.stderr)
    raise SystemExit(2)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="dsd-cloudron")
    sub = parser.add_subparsers(dest="command", required=True)

    new_parser = sub.add_parser("new", help="Scaffold a new Cloudron-ready project.")
    new_parser.add_argument("project_name", help="Human project name, e.g. 'My Shop'.")
    new_parser.add_argument(
        "--output-dir", default=".", help="Where to create the project."
    )
    for dest, _key, default in _TOGGLES:
        if default == "no":
            new_parser.add_argument(
                f"--{dest}",
                dest=dest,
                action="store_true",
                help=f"Enable {dest} (default off).",
            )
        else:
            new_parser.add_argument(
                f"--no-{dest}",
                dest=f"no_{dest}",
                action="store_true",
                help=f"Disable {dest} (default on).",
            )

    # Reconfigure exposes only the two sizing overrides: it re-renders the project's
    # current config and cannot toggle a stack (that needs dependencies and wiring it
    # does not touch), so there are deliberately no --celery/--sso/--no-redis/--no-sendmail
    # flags here.
    recon = sub.add_parser(
        "reconfigure",
        help="Re-render Cloudron artifacts in an existing project, reviewing each change.",
    )
    recon.add_argument(
        "--project-dir",
        default=".",
        help="The scaffolded project to reconfigure (default: current directory).",
    )
    recon.add_argument(
        "--memory-limit",
        type=int,
        default=None,
        help="New memory limit in bytes (default: keep current).",
    )
    recon.add_argument(
        "--health-check-path",
        default=None,
        help="New health check path (default: keep current).",
    )
    return parser.parse_args(argv)


def build_context(args):
    """cookiecutter extra_context from parsed args, validated up front.

    Validation happens here (before cookiecutter runs) so a bad name or an
    impossible toggle combination fails cleanly instead of writing a half-baked
    project to disk and then raising a raw ValueError from CloudronAppConfig.
    """
    # project_name is interpolated verbatim into generated source (the home view's
    # HTML) and docs, and cookiecutter's Jinja2 does not autoescape - a quote,
    # backslash, or angle bracket would break or inject into the rendered files.
    # Restrict the raw name to the characters the message below already promises.
    if not re.fullmatch(r"[A-Za-z0-9 -]+", args.project_name):
        _fail(
            f"{args.project_name!r} contains characters that are not allowed in a "
            "project name; use letters, digits, spaces, or dashes."
        )
    slug = _slugify(args.project_name)
    # isidentifier() alone is not enough: it accepts Python keywords ("class",
    # "import", "for", ...), which would slug fine but make `import <slug>`
    # a SyntaxError, breaking every generated module path. Django's own
    # startproject rejects both, so we do too.
    if not slug.isidentifier() or keyword.iskeyword(slug):
        _fail(
            f"{args.project_name!r} does not reduce to a usable Django project "
            f"package name (got {slug!r}); it must be a valid Python identifier "
            "that is not a reserved word. Start with a letter and use letters, "
            "digits, spaces, or dashes."
        )
    # The slug also becomes the last label of the reverse-DNS app_id, which must
    # start and end with an alphanumeric. A leading/trailing underscore is a legal
    # identifier ("_foo", "foo_") but hyphenates to an invalid id ("com.example.-foo"),
    # rejected only later at `cloudron install`. Reject it up front.
    if slug.startswith("_") or slug.endswith("_"):
        _fail(
            f"{args.project_name!r} reduces to {slug!r}, which starts or ends with "
            "an underscore; that yields an invalid Cloudron app id. Start and end "
            "the name with a letter or digit."
        )
    # app_id is a Cloudron reverse-DNS id, which disallows underscores, so the
    # identifier slug is hyphenated for that segment only.
    context = {
        "project_name": args.project_name,
        "project_slug": slug,
        "app_id": f"com.example.{slug.replace('_', '-')}",
    }
    for dest, key, default in _TOGGLES:
        if default == "no":
            context[key] = "yes" if getattr(args, dest) else "no"
        else:
            context[key] = "no" if getattr(args, f"no_{dest}") else "yes"
    if context["use_celery"] == "yes" and context["use_redis"] == "no":
        _fail(
            "--celery requires Redis (Celery uses the Redis addon as its broker); "
            "drop --no-redis or drop --celery."
        )
    return context


def format_toggle_summary(context):
    """A one-line-per-toggle summary of the resolved scaffold options.

    Printed after creation so the operator can confirm the addons and app stacks
    match intent before installing.
    """
    toggles = [
        ("Redis", context["use_redis"]),
        ("Sendmail", context["use_sendmail"]),
        ("Celery", context["use_celery"]),
        ("SSO", context["use_sso"]),
    ]
    lines = ["Resolved toggles:"]
    for label, value in toggles:
        lines.append(f"- {label}: {'on' if value == 'yes' else 'off'}")
    return "\n".join(lines)


def config_from_context(context):
    """Map cookiecutter answers onto a CloudronAppConfig."""
    return CloudronAppConfig(
        project_name=context["project_slug"],
        app_id=context["app_id"],
        pkg_manager="uv",
        health_check_path="/healthz/",
        enable_redis=context["use_redis"] == "yes",
        enable_sendmail=context["use_sendmail"] == "yes",
        enable_celery=context["use_celery"] == "yes",
        enable_sso=context["use_sso"] == "yes",
        # The scaffolded project wires allauth itself, so the readme may say SSO is
        # fully wired; the retrofit deployer leaves this at its False default.
        greenfield=True,
    )


def _detect_project_slug(project_dir):
    """The project package is the directory holding cloudron_settings.py."""
    matches = sorted(Path(project_dir).glob("*/cloudron_settings.py"))
    if not matches:
        _fail(
            f"could not find the project package (no */cloudron_settings.py) under "
            f"{str(project_dir)!r}; run this inside a scaffolded project."
        )
    return matches[0].parent.name


def _read_project_state(project_dir):
    """Reconstruct a CloudronAppConfig's kwargs from an already-scaffolded project.

    `dsd-cloudron new` does not persist its flags, so reconfigure reads the current
    state back out: the CloudronManifest.json for app_id/title/memoryLimit/
    healthCheckPath and the addon set (redis/sendmail/oidc), the supervisor dir for
    Celery, and the Dockerfile for the package manager. pkg_manager is reconstructed
    rather than assumed, so a re-render reproduces the artifacts faithfully.

    Two caveats on the reconstruction, both currently inert:
      - greenfield is inferred from the absence of the retrofit cloudron_adapters.py,
        which is only a real signal when SSO is on (that file only exists for a
        retrofit SSO deploy). With SSO off no artifact reads greenfield, so a re-render
        is byte-identical whatever it resolves to.
      - version/author/http_port are not read back, so CloudronAppConfig falls back to
        its defaults. Reconfigure never re-renders the manifest body (it syncs only the
        two scalars, preserving version/author/id), and no flat template reads these,
        so the defaults are never written. Read them back here before adding a template
        variable or CLI override that depends on them.
    """
    project_dir = Path(project_dir)
    manifest_path = project_dir / "CloudronManifest.json"
    if not manifest_path.exists():
        _fail(
            f"no CloudronManifest.json in {str(project_dir)!r}; run "
            "`dsd-cloudron reconfigure` inside a project scaffolded by "
            "`dsd-cloudron new`."
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        # A non-UTF-8 manifest raises UnicodeDecodeError before json parses it; abort
        # cleanly for both, matching how packaging._stack_flags_from_disk is hardened.
        _fail(
            f"{manifest_path} could not be read as UTF-8 JSON ({exc}); fix it before "
            "reconfiguring."
        )
    if not isinstance(manifest, dict):
        _fail(f"{manifest_path} is not a JSON object; fix it before reconfiguring.")
    slug = _detect_project_slug(project_dir)
    addons = manifest.get("addons", {})
    # A valid-JSON manifest with addons set to null (or any non-object) would make the
    # `"redis" in addons` checks below raise a raw TypeError; keep it a clean abort.
    if not isinstance(addons, dict):
        _fail(
            f'{manifest_path} "addons" is not a JSON object; fix it before reconfiguring.'
        )
    dockerfile_path = project_dir / "Dockerfile"
    # The Dockerfile is only sniffed for an ASCII marker, so decode leniently: a
    # non-UTF-8 Dockerfile must not crash the reconstruction the way the manifest read
    # (which needs valid JSON) would.
    dockerfile = (
        dockerfile_path.read_text(encoding="utf-8", errors="replace")
        if dockerfile_path.exists()
        else ""
    )
    return {
        "project_name": slug,
        "app_id": manifest.get("id", f"com.example.{slug.replace('_', '-')}"),
        # The uv Dockerfile installs from pyproject.toml; every other manager renders
        # the same requirements.txt block, so req_txt reproduces it byte-for-byte.
        "pkg_manager": "uv" if "COPY pyproject.toml" in dockerfile else "req_txt",
        "title": manifest.get("title", ""),
        "memory_limit": manifest.get("memoryLimit", 1073741824),
        "health_check_path": manifest.get("healthCheckPath", "/"),
        "enable_redis": "redis" in addons,
        "enable_sendmail": "sendmail" in addons,
        "enable_celery": (project_dir / "supervisor" / "celery-worker.conf").exists(),
        "enable_sso": "oidc" in addons,
        # cloudron_adapters.py exists only for a retrofit SSO deploy, so its absence
        # implies greenfield when SSO is on (keeping the adapter pointers and readme
        # wording correct); when SSO is off no artifact reads greenfield (see docstring).
        "greenfield": not (project_dir / slug / "cloudron_adapters.py").exists(),
    }


def reconfigure_config(project_dir, args):
    """Reconstruct the project's config, then apply the sizing overrides.

    Reconfigure re-renders the current configuration; it does not toggle stacks (that
    needs deps + wiring it never touches, and packaging.reconfigure refuses a stack
    change). So the only overrides are --memory-limit and --health-check-path;
    everything else is reconstructed from the project and left as-is. Constructing a
    single CloudronAppConfig lets __post_init__ still reject a project whose on-disk
    state is itself impossible (e.g. a celery worker with the Redis addon removed).
    """
    state = _read_project_state(project_dir)
    if args.memory_limit is not None:
        state["memory_limit"] = args.memory_limit
    if args.health_check_path is not None:
        state["health_check_path"] = args.health_check_path
    try:
        return CloudronAppConfig(**state)
    except ValueError as exc:
        _fail(str(exc))


def run_reconfigure(args):
    """Re-render an existing project's artifacts with a plain-prompt review flow."""
    project_dir = Path(args.project_dir)
    config = reconfigure_config(project_dir, args)

    def _confirm(path):
        # reconfigure is an interactive review flow with no --yes/--automate-all; a
        # closed stdin (piped, redirected from /dev/null, most CI) makes input() raise
        # EOFError. Turn that into the module's clean _fail rather than a raw traceback.
        try:
            answer = input(f"Overwrite {path.relative_to(project_dir)}? [y/N] ")
        except EOFError:
            _fail(
                "reconfigure needs an interactive terminal to review each change; run "
                "it in a tty, or edit the files directly and re-render with a full "
                "`dsd-cloudron new`."
            )
        return answer.strip().lower() in ("y", "yes")

    try:
        # Defensive: greenfield reconstructs config from the same disk signals the stack
        # guard and manifest checks read, so reconfigure's ReconfigureError paths are
        # already pre-empted by _read_project_state (missing/corrupt manifest) and by the
        # reconstruction itself (the stack set matches by construction). This catch only
        # matters if the manifest changes underfoot between the two reads; keep it so that
        # race still aborts cleanly rather than as a traceback.
        result = reconfigure(config, project_dir, confirm=_confirm, output=print)
    except ReconfigureError as exc:
        _fail(str(exc))
    if result.changed:
        print(
            "\nReconfigure complete. Run `cloudron update --app <subdomain>` to roll "
            "these changes out to the running app."
        )
    else:
        print("\nReconfigure complete. No changes were made.")
    return project_dir


def scaffold(args):
    """Render the project skeleton, then the Cloudron artifact set."""
    context = build_context(args)
    try:
        project_dir = cookiecutter(
            str(TEMPLATE_DIR),
            no_input=True,
            extra_context=context,
            output_dir=args.output_dir,
        )
    except OutputDirExistsException as exc:
        # The common re-run case: honor the module's clean-failure promise instead
        # of dumping a raw traceback when the target directory already exists.
        _fail(str(exc))
    try:
        config = config_from_context(context)
        render_all(config, project_dir)
    except Exception as exc:
        # cookiecutter already wrote the skeleton; if the deploy artifacts fail to
        # render, the tree is half-built. Fail cleanly and name the directory to
        # remove, instead of a raw traceback that also blocks a same-name retry.
        _fail(
            f"deploy artifacts failed to render into {project_dir!r}: {exc}. "
            "Remove that directory before retrying."
        )
    return project_dir


def main(argv=None):
    args = parse_args(argv)
    if args.command == "reconfigure":
        run_reconfigure(args)
        return 0
    project_dir = scaffold(args)
    print(f"Created {project_dir}")
    print(format_toggle_summary(build_context(args)))
    print("Next: cd into it, then `cloudron install -l <subdomain>`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
