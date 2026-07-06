# Sphinx build configuration for the dsd-cloudron documentation site.

project = "dsd-cloudron"
author = "Jack Linke"
release = "2026.7.1"

extensions = [
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_design",
]

myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3

# docs/superpowers holds local-only specs and plans; keep it out of the build.
exclude_patterns = ["_build", "superpowers", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_title = "dsd-cloudron"
