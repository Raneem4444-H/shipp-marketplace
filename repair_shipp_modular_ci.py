#!/usr/bin/env python3
"""Repair missing SHIPP modularization files from the last known monolithic app.

Dry-run/preview by default. Never runs git add/commit/push or Databricks deploy.
Only --apply writes into the user's checkout, after backing up existing files.
"""
from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
import sys
from pathlib import Path

from shipp_modularize import render_files, _source_file_checks

HERE = Path(__file__).resolve().parent
ORIGINAL_COMMIT = "ff025734489d0e3f707b7247b83eacb301bc3532"
REQUIRED_SERVICE_FILES = (
    "services/__init__.py",
    "services/dashboard_service.py",
    "services/identity_service.py",
    "services/marketplace_service.py",
    "services/recommendation_service.py",
)


def get_original(repo: Path, original_file: Path | None = None) -> str:
    if original_file:
        return original_file.read_text(encoding="utf-8")
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "show", f"{ORIGINAL_COMMIT}:app.py"],
            check=True, capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError) as e:
        raise RuntimeError(
            f"Cannot read historical app.py from commit {ORIGINAL_COMMIT[:12]}. "
            "Use --original /path/to/saved-full-app.py instead, or fetch the "
            "commit into your local Git checkout. Nothing was modified."
        ) from e
    return proc.stdout


def replacement_files(original: str) -> dict[str, str]:
    generated = render_files(original)
    for name in REQUIRED_SERVICE_FILES:
        generated[name] = (HERE / name).read_text(encoding="utf-8")
    _source_file_checks(original, generated)
    assert "agent.confirm_save(" in generated["ui/pages/ai_advisor.py"]
    assert "marketplace.create_listing(" in generated["ui/pages/donate.py"]
    assert "marketplace.save_listing_images(" in generated["ui/pages/donate.py"]
    assert "marketplace.create_request(" in generated["ui/pages/ai_advisor.py"]
    for name, text in generated.items():
        ast.parse(text, filename=name)
    return generated


def status(repo: Path, files: dict[str,str]):
    print("FILES to create/update in checkout:")
    for name, text in sorted(files.items()):
        dest = repo / name
        if not dest.exists():
            state="MISSING"
        elif dest.read_text(encoding="utf-8") == text:
            state="ALREADY CORRECT"
        elif "placeholder" in dest.read_text(encoding="utf-8").lower() and name.startswith("ui/pages/"):
            state="REPLACE PLACEHOLDER"
        else:
            state="DIFFERENT - BACKUP BEFORE OVERWRITE"
        print(f"  {state:32} {name}")


def write_preview(output: Path, files: dict[str, str]):
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"Preview target must be empty: {output}")
    for name, text in files.items():
        dest = output / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    print(f"PREVIEW created: {output} ({len(files)} files)")


def apply_locally(repo: Path, files: dict[str, str]):
    back = repo / ".shipp-refactor-repair-backup"
    for name, text in files.items():
        dest = repo / name
        if dest.exists() and dest.read_text(encoding="utf-8") != text:
            saved = back / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            if saved.exists():
                raise RuntimeError(f"Existing backup conflict: {saved}. Aborting safely.")
            shutil.copy2(dest, saved)
    for name, text in files.items():
        dest = repo / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    print(f"LOCAL APPLY COMPLETED: {len(files)} files; backup directory: {back}")
    print("No Git actions were run. No push. No deployment.")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument("--original", type=Path, help="Optional complete pre-modular app.py")
    action=p.add_mutually_exclusive_group()
    action.add_argument("--preview", type=Path, help="Write to separate review directory")
    action.add_argument("--apply", action="store_true", help="Apply to local checkout (backups created)")
    args=p.parse_args()
    repo=args.repo.resolve()
    if not (repo/'app.py').is_file():
        p.error(f"No app.py in {repo}")
    actual=(repo/'app.py').read_text(encoding="utf-8")
    if "from ui import legacy_core as core" not in actual:
        p.error("Not the expected thin-router checkout; refusing to apply to a different app.py")
    original=get_original(repo,args.original)
    files=replacement_files(original)
    status(repo,files)
    if args.apply:
        apply_locally(repo,files)
    elif args.preview:
        output=args.preview.resolve()
        if output==repo or repo in output.parents:
            p.error("Preview must be outside checkout")
        write_preview(output,files)
    else:
        print("READ ONLY: No changes. Use --preview for review, then --apply when ready.")

if __name__ == "__main__":
    main()
