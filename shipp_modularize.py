#!/usr/bin/env python3
"""Safely split SHIPP's existing Streamlit app into a reviewable multipage app.

NO network requests. NO git commands. NO GitHub push. NO Databricks deployment.
The converter copies the exact existing donor/requester functions; business
behavior is not recreated, omitted or reimplemented from memory.

Usage:
  python shipp_modularize.py --repo /path/to/shipp-marketplace --output /tmp/shipp-preview
  python shipp_modularize.py --repo /path/to/shipp-marketplace --apply

The default preview writes ONLY to --output. --apply is explicit, creates a
backup of the original app.py, then installs files in the checked-out repo.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import shutil
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE_NAMES = {
    "render_home": ("home.py", "render_home()"),
    "render_explore": ("marketplace.py", "render_explore()"),
    "render_donor": ("donate.py", "render_donor()"),
    "render_requester": ("ai_advisor.py", "render_requester()"),
}
HEADER_MARKER = "# ------------------------------------------------------------\n# Shared marketplace brand."
DONOR_MARKER = "# ============================================================\n# DONOR JOURNEY"
FOOTER_MARKER = "# ------------------------------------------------------------\n# Professional project footer"


class LayoutError(RuntimeError):
    pass


def extracted_functions(source: str) -> dict[str, str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    found: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in PAGE_NAMES:
            if node.name in found:
                raise LayoutError(f"Duplicate {node.name} definitions")
            found[node.name] = "".join(lines[node.lineno - 1:node.end_lineno])
    missing = sorted(set(PAGE_NAMES) - set(found))
    if missing:
        raise LayoutError(f"Missing current-app functions: {missing}. No files changed.")
    return found


def _strip_streamlit_page_config(prefix: str) -> str:
    """Remove ONLY the existing top-level set_page_config call from core."""
    tree = ast.parse(prefix)
    lines = prefix.splitlines(keepends=True)
    page_nodes = [
        n for n in tree.body
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Attribute)
        and isinstance(n.value.func.value, ast.Name)
        and n.value.func.value.id == "st" and n.value.func.attr == "set_page_config"
    ]
    if len(page_nodes) != 1:
        raise LayoutError("Expected exactly one top-level st.set_page_config call")
    node = page_nodes[0]
    for index in range(node.lineno - 1, node.end_lineno):
        lines[index] = ""
    return "".join(lines)


def _build_core(original: str) -> str:
    if HEADER_MARKER not in original or DONOR_MARKER not in original:
        raise LayoutError("Cannot locate existing app markers. No files changed.")
    prefix = original[:original.index(HEADER_MARKER)]
    prefix = _strip_streamlit_page_config(prefix)
    old_root = "ROOT_DIR = Path(__file__).resolve().parent"
    if prefix.count(old_root) != 1:
        raise LayoutError("Cannot safely relocate ROOT_DIR")
    prefix = prefix.replace(old_root, "ROOT_DIR = Path(__file__).resolve().parents[1]", 1)
    # Preserve current operational bootstrap, caches, Agent and listing renderer.
    # Per-rerun session initialization is added below for every browser session.
    prefix += textwrap.dedent('''

    def initialize_session() -> None:
        """Initialize independent mutable state on every new Streamlit session."""
        import copy
        for key, default_value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = copy.deepcopy(default_value)
    ''')
    return prefix


def _format_component(name: str, raw_source: str) -> str:
    return (
        f'"""SHIPP {name}; exact markup lifted from the original entry point."""\n'
        'from __future__ import annotations\n'
        'import streamlit as st\n\n'
        f'def {name}() -> None:\n'
        + textwrap.indent(raw_source.strip() + "\n", "    ")
    )


def _build_page(name: str, body: str, original: str) -> str:
    # Preserve existing business functions verbatim. Only Home's navigation
    # reference is updated, because st.Page files use script paths here.
    if name == "render_home":
        body = body.replace('st.switch_page(EXPLORE_PAGE)',
                            'st.switch_page("ui/pages/marketplace.py")')
    # Continue using the same existing marketplace and Agent instances.
    header = (
        '"""Auto-extracted from the original SHIPP app; review before deployment."""\n'
        'from __future__ import annotations\n'
        'from ui.legacy_core import *  # noqa: F403,F401 — original dependencies\n'
    )
    if name in ("render_home", "render_explore"):
        header += 'from services.marketplace_service import MarketplaceService\n'
        # Reuse the existing query logic, now through the service layer.
        body = body.replace(
            'marketplace.list_available_listings(',
            'catalog.list_available_listings(',
        )
        colon = body.find('\n')
        body = body[:colon + 1] + '    catalog = MarketplaceService(marketplace)\n' + body[colon + 1:]
    if name == "render_explore":
        import re
        match = re.search(r"(?m)^CATALOG_PAGE_SIZE\s*=\s*(\d+)\s*$", original)
        if match is None:
            raise LayoutError("Existing Explore catalog page-size constant missing")
        header += f'CATALOG_PAGE_SIZE = {match.group(1)}\n'
    header += "\n" + body.rstrip() + "\n\n" + PAGE_NAMES[name][1] + "\n"
    return header


def render_files(original_app: str) -> dict[str, str]:
    funcs = extracted_functions(original_app)
    core = _build_core(original_app)
    start = original_app.index(HEADER_MARKER)
    donor = original_app.index(DONOR_MARKER, start)
    footer = original_app.index(FOOTER_MARKER, donor)
    brand_raw = original_app[start:donor]
    # Drop only the header comment, preserving the real st.markdown body.
    mark = brand_raw.find("st.markdown(")
    if mark < 0:
        raise LayoutError("Missing SHIPP brand markup")
    brand_raw = brand_raw[mark:]
    footer_raw = original_app[footer:]
    mark = footer_raw.find("st.markdown(")
    if mark < 0:
        raise LayoutError("Missing footer markup")
    footer_raw = footer_raw[mark:]
    out: dict[str, str] = {
        "ui/legacy_core.py": core,
        "ui/components/branding.py": _format_component("render_brand", brand_raw),
        "ui/components/footer.py": _format_component("render_footer", footer_raw),
    }
    for function_name, (filename, _) in PAGE_NAMES.items():
        out[f"ui/pages/{filename}"] = _build_page(function_name, funcs[function_name], original_app)
    return out


def _base_package_files() -> dict[str, str]:
    paths = [HERE / "app.py", HERE / "shipp_modularize.py"]
    paths.extend((HERE / "test" / "unit").glob("test_shipp_*.py"))
    for folder in ["ui", "services"]:
        paths.extend(p for p in (HERE / folder).rglob("*.py") if p.is_file())
    out = {}
    for path in paths:
        out[path.relative_to(HERE).as_posix()] = path.read_text(encoding="utf-8")
    return out


def _source_file_checks(original: str, output: dict[str, str]) -> None:
    expected_functions = extracted_functions(original)
    for name, (filename, _) in PAGE_NAMES.items():
        path = f"ui/pages/{filename}"
        assert f"def {name}(" in output[path], f"Missing {name} in {path}"
        if name in ("render_donor", "render_requester"):
            # These two user-sensitive functions are copied with no changes.
            assert expected_functions[name] in output[path], f"Business-flow source changed: {name}"
    for string in ["marketplace.create_listing(", "marketplace.create_request(",
                   "agent.confirm_save(", "marketplace.save_listing_images("]:
        if string not in original:
            raise LayoutError(f"Original app is missing a critical flow: {string}")
        if not any(string in output[p] for p in
                   ["ui/pages/donate.py", "ui/pages/ai_advisor.py"]):
            raise LayoutError(f"Refactor dropped a critical flow: {string}")
    for path, contents in output.items():
        try:
            compile(contents, path, "exec")
        except SyntaxError as error:
            raise LayoutError(f"Generated {path} failed syntax: {error}") from error


def _write_files(target: Path, files: dict[str, str]) -> None:
    for name, body in sorted(files.items()):
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(body, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd(),
                        help="Local SHIPP Git checkout containing the CURRENT original app.py")
    parser.add_argument("--output", type=Path, help="Create a separate review directory")
    parser.add_argument("--apply", action="store_true",
                        help="Explicitly install into repo after backing up original app.py")
    args = parser.parse_args()
    repo = args.repo.resolve()
    existing = repo / "app.py"
    if not existing.exists():
        parser.error(f"No existing root app.py in {repo}")
    if args.apply and args.output:
        parser.error("Use either --apply or --output, not both")
    if not args.apply and not args.output:
        parser.error("Choose --output for safe preview, or --apply explicitly")

    original = existing.read_text(encoding="utf-8")
    if "ui.components.navbar import create_navigation" in original:
        parser.error("This repo already looks modularized; use its backup, not a second migration")
    files = _base_package_files()
    files.update(render_files(original))
    _source_file_checks(original, files)

    if args.apply:
        backup_dir = repo / ".shipp-refactor-backup"
        backup_dir.mkdir(exist_ok=True)
        digest = hashlib.sha256(original.encode("utf-8")).hexdigest()[:12]
        backup = backup_dir / f"app-{digest}.py"
        if not backup.exists():
            shutil.copy2(existing, backup)
        target = repo
        print(f"BACKUP: {backup}")
    else:
        target = args.output.resolve()
        if repo == target or repo in target.parents:
            raise LayoutError("Preview must be outside the repository (not a deployment)")
        if target.exists() and any(target.iterdir()):
            raise LayoutError(f"Preview directory is not empty: {target}")
    _write_files(target, files)
    print(f"PASS: Generated {len(files)} .py files in {target}")
    print("PASS: Existing donor/requester business function text preserved exactly")
    print("NO GIT ACTIONS. NO PUSH. NO DEPLOYMENT.")


if __name__ == "__main__":
    main()
