# Configuration file for the Sphinx documentation builder.
import os
import sys
sys.path.insert(0, os.path.abspath('../../src'))

# -- Project information -----------------------------------------------------
project = 'snap_simulate'
copyright = '2026, Tanner A. Wilcoxson'
author = 'Tanner A. Wilcoxson'
release = '0.0.1'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.intersphinx',
    'sphinx.ext.mathjax',
]


templates_path = ['_templates']
exclude_patterns = []
autodoc_mock_imports = ['hoomd']

# -- Options for HTML output -------------------------------------------------
html_theme = 'furo'
html_static_path = ['_static']
html_title = "snap_simulate documentation"
html_theme_options = {
    "light_logo": "logo_light.png",
    "dark_logo": "logo.png",
    "sidebar_hide_name": True,
}


