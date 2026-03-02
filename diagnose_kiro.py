#!/usr/bin/env python
"""
Diagnostic script to troubleshoot Kiro model discovery.
Run this to see why Kiro models aren't being auto-discovered.
"""

import sys
import os

print("\n" + "="*70)
print("Kiro Discovery Diagnostic")
print("="*70)

if os.name != "nt":
    print("\n✗ This tool only works on Windows")
    sys.exit(1)

print("\n1. Checking WSL availability...")
try:
    from src.aicodereviewer.path_utils import is_wsl_available, get_wsl_distros
    if is_wsl_available():
        print("   ✓ WSL is available")
        distros = get_wsl_distros()
        print(f"   ✓ Found {len(distros)} WSL distribution(s):")
        for distro in distros:
            print(f"     - {distro}")
    else:
        print("   ✗ WSL is not available")
        sys.exit(1)
except Exception as e:
    print(f"   ✗ Error: {e}")
    sys.exit(1)

print("\n2. Checking Kiro in each distro...")
try:
    from src.aicodereviewer.path_utils import run_in_wsl
    
    for distro in distros:
        print(f"\n   Testing: {distro}")
        
        # Test 1: Check if kiro exists in PATH
        rc, stdout, stderr = run_in_wsl(
            ["which", "kiro"],
            distro=distro,
            timeout=5
        )
        if rc == 0:
            print(f"   ✓ Kiro found at: {stdout.strip()}")
        else:
            print(f"   ✗ Kiro not in PATH")
        
        # Test 2: Try to run kiro --help
        rc, stdout, stderr = run_in_wsl(
            ["kiro", "--help"],
            distro=distro,
            timeout=5
        )
        if rc == 0:
            print(f"   ✓ 'kiro --help' works!")
            # Try to find model option
            import re
            m = re.search(r"--model\b[^(]*\(choices:\s*([^)]+)\)", stdout, re.DOTALL)
            if m:
                choices_text = m.group(1)
                quoted_models = re.findall(r'"([^"]+)"', choices_text)
                print(f"   ✓ Found {len(quoted_models)} models:")
                for model in quoted_models[:5]:  # Show first 5
                    print(f"     - {model}")
                if len(quoted_models) > 5:
                    print(f"     ... and {len(quoted_models)-5} more")
            else:
                print("   ⚠ Kiro help doesn't show model option")
        else:
            print(f"   ✗ 'kiro --help' failed with code {rc}")
            if stderr:
                print(f"     Error: {stderr[:100]}")
                
except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70)
print("Troubleshooting Steps")
print("="*70)
print("""
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
""")
print("="*70 + "\n")
