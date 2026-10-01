"""SHIPP data pipeline library.

Rule: modules here contain reusable, testable functions only. They never write tables on
import and never read secrets. Notebooks under notebooks/ are the only writers of tables.
"""
