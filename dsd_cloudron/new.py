"""Greenfield scaffolder: `dsd-cloudron new <name>`.

Renders a Cloudron-ready Django project from the bundled cookiecutter template,
then renders the deploy artifacts through the shared packaging core.
"""

import argparse
import re
import sys
from pathlib import Path

from cookiecutter.main import cookiecutter

from .packaging import CloudronAppConfig, render_all

TEMPLATE_DIR = Path(__file__).parent / "project_template"

# (flag dest, cookiecutter key, default "yes"/"no").
# Infra defaults on; app-stack defaults off (section 6, lean).
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
    return parser.parse_args(argv)


def build_context(args):
    """cookiecutter extra_context from parsed args, validated up front.

    Validation happens here (before cookiecutter runs) so a bad name or an
    impossible toggle combination fails cleanly instead of writing a half-baked
    project to disk and then raising a raw ValueError from CloudronAppConfig.
    """
    slug = _slugify(args.project_name)
    if not slug.isidentifier():
        _fail(
            f"{args.project_name!r} does not reduce to a valid Python identifier "
            f"(got {slug!r}); it names the Django project package. Start with a "
            "letter and use letters, digits, spaces, or dashes."
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
    )


def scaffold(args):
    """Render the project skeleton, then the Cloudron artifact set."""
    context = build_context(args)
    project_dir = cookiecutter(
        str(TEMPLATE_DIR),
        no_input=True,
        extra_context=context,
        output_dir=args.output_dir,
    )
    config = config_from_context(context)
    render_all(config, project_dir)
    return project_dir


def main(argv=None):
    args = parse_args(argv)
    if args.command == "new":
        project_dir = scaffold(args)
        print(f"Created {project_dir}")
        print("Next: cd into it, then `cloudron install -l <subdomain>`.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
