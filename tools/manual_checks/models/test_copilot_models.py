#!/usr/bin/env python
"""Quick smoke-test to verify Copilot models are discovered via the SDK."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
for bootstrap_path in (str(REPO_ROOT), str(SRC_ROOT)):
    if bootstrap_path not in sys.path:
        sys.path.insert(0, bootstrap_path)

from src.aicodereviewer.backends.models import _copilot_models_cache, get_copilot_models

_copilot_models_cache.clear()

models = get_copilot_models()

print("\n" + "=" * 60)
print("Copilot Model Discovery Test (github-copilot-sdk)")
print("=" * 60)

if models:
    print(f"✓ Successfully discovered {len(models)} models:\n")
    for index, model in enumerate(models, 1):
        print(f"  {index:2}. {model}")
    print("\n✓ GUI dropdown should now populate with these models!")
    sys.exit(0)

print("✗ Failed to discover models")
print("  Ensure the Copilot CLI is installed, authenticated, and in PATH.")
print("  Run 'copilot' then /login, or set GH_TOKEN / GITHUB_TOKEN.")
sys.exit(1)