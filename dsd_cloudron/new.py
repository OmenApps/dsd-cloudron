"""Greenfield scaffolder: `dsd-cloudron new <name>`.

Renders a Cloudron-ready Django project from the bundled cookiecutter template,
then renders the deploy artifacts through the shared packaging core.
"""

import argparse
import keyword
import re
import sys
from pathlib import Path

from cookiecutter.exceptions import OutputDirExistsException
from cookiecutter.main import cookiecutter

from .packaging import CloudronAppConfig, render_all

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
    # argparse requires the "new" subcommand (the only one), so it exits before
    # parse_args returns if it is missing; args.command is always "new" here.
    args = parse_args(argv)
    project_dir = scaffold(args)
    print(f"Created {project_dir}")
    print("Next: cd into it, then `cloudron install -l <subdomain>`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
