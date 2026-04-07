#!/usr/bin/env python
"""Test script for model auto-loading functionality."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
for bootstrap_path in (str(REPO_ROOT), str(SRC_ROOT)):
    if bootstrap_path not in sys.path:
        sys.path.insert(0, bootstrap_path)

from aicodereviewer.backends.health import _auto_loaded_models, get_local_models


def test_model_discovery() -> None:
    """Test model discovery with auto-loading for different API types."""
    print("=" * 70)
    print("Testing Model Discovery with Auto-Loading")
    print("=" * 70)
    print()

    test_cases = [
        ("LM Studio", "http://localhost:1234", "lmstudio"),
        ("Ollama", "http://localhost:11434", "ollama"),
        ("OpenAI-compatible", "http://localhost:1234", "openai"),
        ("Anthropic-compatible", "http://localhost:1234", "anthropic"),
    ]

    for name, url, api_type in test_cases:
        print(f"{name} ({url}, type={api_type}):")
        try:
            models = get_local_models(url, api_type)
            if models:
                print(f"  ✓ Found {len(models)} model(s)")
                print(f"    First 3: {models[:3]}")
            else:
                print("  ○ No models found (server may not be running)")

            cache_key = (url, api_type)
            if cache_key in _auto_loaded_models:
                print(f"  ★ Auto-loaded: {_auto_loaded_models[cache_key]}")
        except Exception as exc:
            print(f"  ✗ Error: {exc}")
        print()

    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Total auto-loaded models: {len(_auto_loaded_models)}")
    for (url, api_type), model_id in _auto_loaded_models.items():
        print(f"  - {api_type} @ {url}: {model_id}")
    print()
    print("Note: Auto-loaded models will be unloaded when the program exits.")


if __name__ == "__main__":
    test_model_discovery()