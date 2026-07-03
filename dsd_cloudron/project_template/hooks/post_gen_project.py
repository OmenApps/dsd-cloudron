"""Post-generation pruning for disabled toggles.

Cookiecutter runs this from the generated project root. Remove files that only
make sense for a feature that the user toggled off.
"""

import os

PROJECT_SLUG = "{{ cookiecutter.project_slug }}"


def remove(paths):
    for path in paths:
        if os.path.exists(path):
            os.remove(path)


def main():
    if "{{ cookiecutter.use_celery }}" == "no":
        remove([os.path.join(PROJECT_SLUG, "celery.py")])
    if "{{ cookiecutter.use_ninja }}" == "no":
        remove([os.path.join(PROJECT_SLUG, "core", "api.py")])
    if "{{ cookiecutter.use_sso }}" == "no":
        # adapters.py imports allauth, which is only a dependency when SSO is on.
        remove([os.path.join(PROJECT_SLUG, "accounts", "adapters.py")])


if __name__ == "__main__":
    main()
