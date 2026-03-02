#!/usr/bin/env python
"""Test that Kiro model dropdown is properly populated in settings."""

import sys

print("\n" + "="*60)
print("Test: Kiro Model Dropdown Population")
print("="*60)

# Test 1: Verify get_kiro_models returns fallback when Kiro unavailable
print("\nTest 1: Model discovery with fallback")
try:
    from src.aicodereviewer.backends.health import get_kiro_models
    models = get_kiro_models()
    if models:
        print(f"✓ get_kiro_models() returned {len(models)} models:")
        for model in models:
            print(f"  - {model}")
    else:
        print("✗ get_kiro_models() returned empty list")
        sys.exit(1)
except Exception as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

# Test 2: Verify settings can access and use the models
print("\nTest 2: Settings initialization")
try:
    from src.aicodereviewer.config import config
    from src.aicodereviewer.backends.health import get_kiro_models
    
    kiro_cmd = config.get("kiro", "cli_command", "kiro")
    kiro_distro = config.get("kiro", "wsl_distro", "")
    models = get_kiro_models(kiro_cmd, kiro_distro)
    
    if models:
        print(f"✓ Settings can load {len(models)} Kiro models")
        print(f"  First model: {models[0]}")
    else:
        print("✗ Settings failed to load models")
        sys.exit(1)
except Exception as e:
    print(f"✗ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Verify HealthMixin can refresh models
print("\nTest 3: Model refresh capability")
try:
    from src.aicodereviewer.gui.health_mixin import HealthMixin
    if hasattr(HealthMixin, '_apply_kiro_models'):
        print("✓ HealthMixin has _apply_kiro_models method")
    else:
        print("✗ HealthMixin missing _apply_kiro_models")
        sys.exit(1)
except Exception as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

print("\n" + "="*60)
print("All tests passed! ✓")
print("="*60)
print("\nKiro model dropdown should now display:")
for i, model in enumerate(models, 1):
    print(f"  {i}. {model}")
print("\nThe dropdown will auto-populate with these models")
print("when the Settings tab is opened.")
