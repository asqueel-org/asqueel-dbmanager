"""Public DB Manager manual, with the shared Asqueel documentation theme."""

from importlib.metadata import version as _package_version

project = "Asqueel DB Manager"
copyright = "2025-2026, Softwell S.r.l."
author = "Softwell S.r.l."
release = _package_version("asqueel-dbmanager")
version = release
language = "en"
extensions = ["myst_parser"]
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
# Only the public manual is built; local planning notes stay outside it.
include_patterns = ["index.rst", "guide/**"]
exclude_patterns = ["_build", ".DS_Store"]
myst_heading_anchors = 3
html_theme = "sphinx_rtd_theme"
html_title = "Asqueel DB Manager — Developer documentation"
html_logo = "../assets/branding/asqueel-dbmanager-inverse.svg"
html_favicon = "../assets/branding/asqueel-monogram.svg"
html_static_path = ["_static"]
html_css_files = ["brand.css"]
html_theme_options = {
    "logo_only": True,
    "collapse_navigation": False,
    "navigation_depth": 3,
}
html_context = {
    "display_github": True,
    "github_user": "asqueel-org",
    "github_repo": "asqueel-dbmanager",
    "github_version": "main",
    "conf_py_path": "/docs/",
}
