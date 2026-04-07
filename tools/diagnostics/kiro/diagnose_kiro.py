#!/usr/bin/env python
"""Diagnostic script to troubleshoot Kiro model discovery on Windows."""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
for bootstrap_path in (str(REPO_ROOT), str(SRC_ROOT)):
    if bootstrap_path not in sys.path:
        sys.path.insert(0, bootstrap_path)

print("\n" + "=" * 70)
print("Kiro Discovery Diagnostic")
print("=" * 70)

if os.name != "nt":
    print("\nThis tool only works on Windows")
    sys.exit(1)

print("\n1. Checking WSL availability...")
try:
    from src.aicodereviewer.path_utils import get_wsl_distros, is_wsl_available

    if is_wsl_available():
        print("   ✓ WSL is available")
        distros = get_wsl_distros()
        print(f"   ✓ Found {len(distros)} WSL distribution(s):")
        for distro in distros:
            print(f"     - {distro}")
    else:
        print("   ✗ WSL is not available")
        sys.exit(1)
except Exception as exc:
    print(f"   ✗ Error: {exc}")
    sys.exit(1)

print("\n2. Checking Kiro in each distro...")
try:
    from src.aicodereviewer.path_utils import run_in_wsl

    for distro in distros:
        print(f"\n   Testing: {distro}")

        rc, stdout, stderr = run_in_wsl(["which", "kiro"], distro=distro, timeout=5)
        if rc == 0:
            print(f"   ✓ Kiro found at: {stdout.strip()}")
        else:
            print("   ✗ Kiro not in PATH")

        rc, stdout, stderr = run_in_wsl(["kiro", "--help"], distro=distro, timeout=5)
        if rc == 0:
            print("   ✓ 'kiro --help' works!")
            import re

            match = re.search(r"--model\b[^(]*\(choices:\s*([^)]+)\)", stdout, re.DOTALL)
            if match:
                choices_text = match.group(1)
                quoted_models = re.findall(r'"([^"]+)"', choices_text)
                print(f"   ✓ Found {len(quoted_models)} models:")
                for model in quoted_models[:5]:
                    print(f"     - {model}")
                if len(quoted_models) > 5:
                    print(f"     ... and {len(quoted_models) - 5} more")
            else:
                print("   ⚠ Kiro help doesn't show model option")
        else:
            print(f"   ✗ 'kiro --help' failed with code {rc}")
            if stderr:
                print(f"     Error: {stderr[:100]}")

except Exception as exc:
    print(f"   ✗ Error: {exc}")
    import traceback

    traceback.print_exc()

print("\n" + "=" * 70)
print("Troubleshooting Steps")
print("=" * 70)
print(
    """
If Kiro is not found:

1. Verify Kiro is installed in WSL:
   wsl -d Ubuntu which kiro

2. If not found, install Kiro:
   wsl -d Ubuntu bash -c "curl -fsSL https://cli.kiro.dev/install.sh | bash"

3. After installation, test:
   wsl -d Ubuntu kiro --help

4. If still not working, check PATH:
   wsl -d Ubuntu echo $PATH

5. Make sure Kiro is in one of the PATH directories

Once Kiro is properly installed and accessible:
- Restart the AICodeReviewer GUI
- Open Settings → Kiro CLI
- Click the ↻ button to refresh models
- Models should auto-populate from kiro --help
"""
)
print("=" * 70 + "\n")