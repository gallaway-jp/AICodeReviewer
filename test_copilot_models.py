#!/usr/bin/env python
"""Quick test to verify Copilot models are discovered correctly."""
import sys
from src.aicodereviewer.backends.models import get_copilot_models, _copilot_models_cache

# Clear cache to test fresh discovery
_copilot_models_cache.clear()

models = get_copilot_models()

print("\n" + "="*60)
print("Copilot Model Discovery Test")
print("="*60)

if models:
    print(f"✓ Successfully discovered {len(models)} models:\n")
    for i, model in enumerate(models, 1):
        print(f"  {i:2}. {model}")
    print("\n✓ GUI dropdown should now populate with these models!")
    sys.exit(0)
else:
    print("✗ Failed to discover models")
    print("  Check that 'copilot --help' is working correctly")
    sys.exit(1)
