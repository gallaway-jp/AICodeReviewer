#!/usr/bin/env python
"""Quick smoke-test to verify Copilot models are discovered via the SDK."""
import sys
from src.aicodereviewer.backends.models import get_copilot_models, _copilot_models_cache

# Clear cache to test fresh discovery
_copilot_models_cache.clear()

models = get_copilot_models()

print("\n" + "="*60)
print("Copilot Model Discovery Test (github-copilot-sdk)")
print("="*60)

if models:
    print(f"✓ Successfully discovered {len(models)} models:\n")
    for i, model in enumerate(models, 1):
        print(f"  {i:2}. {model}")
    print("\n✓ GUI dropdown should now populate with these models!")
    sys.exit(0)
else:
    print("✗ Failed to discover models")
    print("  Ensure the Copilot CLI is installed, authenticated, and in PATH.")
    print("  Run 'copilot' then /login, or set GH_TOKEN / GITHUB_TOKEN.")
    sys.exit(1)
