#!/usr/bin/env python
"""Debug Kiro help output in WSL."""

import sys
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
for bootstrap_path in (str(REPO_ROOT), str(SRC_ROOT)):
    if bootstrap_path not in sys.path:
        sys.path.insert(0, bootstrap_path)

print("=" * 60)
print("Debugging Kiro Model Discovery")
print("=" * 60)

print(f"\nOS: {os.name}")

if os.name == "nt":
    print("\nAttempting to run 'kiro --help' in WSL...")

    print("\n1. Using run_in_wsl with default distro:")
    try:
        from src.aicodereviewer.path_utils import run_in_wsl

        rc, stdout, stderr = run_in_wsl(["kiro", "--help"], distro=None, timeout=5)
        print(f"   Return code: {rc}")
        print(f"   Stdout length: {len(stdout)} chars")
        print(f"   Stderr length: {len(stderr)} chars")

        if stdout:
            print("\n   First 500 chars of stdout:")
            print("   " + "\n   ".join(stdout[:500].split("\n")))

        if stderr:
            print("\n   Stderr output:")
            print("   " + stderr[:500])

        import re

        match = re.search(r"--model\b[^(]*\(choices:\s*([^)]+)\)", stdout, re.DOTALL)
        if match:
            print("\n   ✓ Found model option in help!")
            choices_text = match.group(1)
            quoted_models = re.findall(r'"([^"]+)"', choices_text)
            print(f"   Models found: {quoted_models}")
        else:
            print("\n   ✗ Could not find model option in help")

    except Exception as exc:
        print(f"   ✗ Failed: {exc}")
        import traceback

        traceback.print_exc()

    print("\n2. Direct execution (fallback):")
    try:
        from src.aicodereviewer.backends.models import _run_quiet

        rc, stdout, stderr = _run_quiet(["kiro", "--help"], timeout=5)
        print(f"   Return code: {rc}")
        print(f"   Stdout length: {len(stdout)} chars")
        if stderr:
            print(f"   Stderr: {stderr[:200]}")

    except Exception as exc:
        print(f"   ✗ Failed: {exc}")
else:
    print("\nNot on Windows, skipping WSL tests")