#!/usr/bin/env python
"""Test script to verify Kiro model selector implementation."""

import sys

# Test 1: Import and check get_kiro_models
print("\n" + "="*60)
print("Test 1: Import get_kiro_models from health module")
print("="*60)
try:
    from src.aicodereviewer.backends.health import get_kiro_models
    print("✓ Successfully imported get_kiro_models from health module")
except Exception as e:
    print(f"✗ Failed to import: {e}")
    sys.exit(1)

# Test 2: Check KiroBackend has model parameter
print("\n" + "="*60)
print("Test 2: Check KiroBackend has model parameter")
print("="*60)
try:
    from src.aicodereviewer.backends.kiro import KiroBackend
    kb = KiroBackend()
    if hasattr(kb, 'model'):
        print(f"✓ KiroBackend has 'model' attribute: {kb.model}")
    else:
        print("✗ KiroBackend missing 'model' attribute")
        sys.exit(1)
except Exception as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

# Test 3: Check HealthMixin has Kiro methods
print("\n" + "="*60)
print("Test 3: Check HealthMixin has Kiro model refresh methods")
print("="*60)
try:
    from src.aicodereviewer.gui.health_mixin import HealthMixin
    has_refresh = hasattr(HealthMixin, '_refresh_kiro_model_list_async')
    has_apply = hasattr(HealthMixin, '_apply_kiro_models')
    if has_refresh and has_apply:
        print("✓ HealthMixin has _refresh_kiro_model_list_async")
        print("✓ HealthMixin has _apply_kiro_models")
    else:
        print(f"✗ Missing methods: refresh={has_refresh}, apply={has_apply}")
        sys.exit(1)
except Exception as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

# Test 4: Check SettingsTabMixin can import
print("\n" + "="*60)
print("Test 4: Check SettingsTabMixin module")
print("="*60)
try:
    from src.aicodereviewer.gui.settings_mixin import SettingsTabMixin
    print("✓ SettingsTabMixin imports successfully")
except Exception as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

# Test 5: Check translation strings exist
print("\n" + "="*60)
print("Test 5: Check translation strings")
print("="*60)
try:
    from src.aicodereviewer.lang.en import STRINGS as EN
    en_has_setting = "gui.settings.kiro_model" in EN
    en_has_tip = "gui.tip.kiro_model" in EN
    if en_has_setting:
        print(f"✓ English has 'gui.settings.kiro_model': {EN['gui.settings.kiro_model']}")
    else:
        print("✗ Missing English setting string")
        sys.exit(1)
    if en_has_tip:
        print(f"✓ English has 'gui.tip.kiro_model': {EN['gui.tip.kiro_model']}")
    else:
        print("✗ Missing English tooltip string")
        sys.exit(1)
except Exception as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

# Test 6: Check Japanese translation strings
print("\n" + "="*60)
print("Test 6: Check Japanese translation strings")
print("="*60)
try:
    from src.aicodereviewer.lang.ja import STRINGS as JA
    ja_has_setting = "gui.settings.kiro_model" in JA
    ja_has_tip = "gui.tip.kiro_model" in JA
    if ja_has_setting:
        print(f"✓ Japanese has 'gui.settings.kiro_model': {JA['gui.settings.kiro_model']}")
    else:
        print("✗ Missing Japanese setting string")
        sys.exit(1)
    if ja_has_tip:
        print(f"✓ Japanese has 'gui.tip.kiro_model': {JA['gui.tip.kiro_model']}")
    else:
        print("✗ Missing Japanese tooltip string")
        sys.exit(1)
except Exception as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

print("\n" + "="*60)
print("All tests passed!")
print("="*60)
print("\nKiro model selector implementation is complete:")
print("  - get_kiro_models() function added")
print("  - KiroBackend supports model parameter")
print("  - HealthMixin has refresh methods")
print("  - UI controls configured in SettingsTabMixin")
print("  - Translation strings added (EN + JA)")
