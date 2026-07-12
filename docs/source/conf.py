from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))
os.environ.setdefault("PYTHONPATH", str(SRC))

project = "Polyhedron"
author = "RhineQC GmbH"
copyright = "2026, RhineQC GmbH"
version = "0.3"
release = "0.3.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx.ext.duration",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

autosummary_generate = True
autoclass_content = "both"
autodoc_member_order = "bysource"
autodoc_typehints = "description"
napoleon_google_docstring = True
napoleon_numpy_docstring = False

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pyomo": ("https://pyomo.readthedocs.io/en/stable/", None),
    "cvxpy": ("https://www.cvxpy.org/", None),
    "pyscipopt": ("https://pyscipopt.readthedocs.io/en/latest/", None),
}

# sphinx-copybutton and sphinx-design are optional; degrade gracefully if
# not installed.
try:
    import sphinx_copybutton  # noqa: F401

    extensions.append("sphinx_copybutton")
except ImportError:
    pass

try:
    import sphinx_design  # noqa: F401

    extensions.append("sphinx_design")
except ImportError:
    pass

try:
    import sphinx_rtd_theme  # noqa: F401

    html_theme = "sphinx_rtd_theme"
except ImportError:
    html_theme = "alabaster"

html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_logo = "_static/polyhedron-logo.png"
html_favicon = "_static/polyhedron-favicon.png"
html_title = "Polyhedron Documentation"
html_theme_options = (
    {"navigation_depth": 3, "collapse_navigation": False, "logo_only": True}
    if html_theme == "sphinx_rtd_theme"
    else {}
)
