#!/usr/bin/env python
"""Debug Kiro help output in WSL."""

import sys
import os

print("="*60)
print("Debugging Kiro Model Discovery")
print("="*60)

print(f"\nOS: {os.name}")

if os.name == "nt":
    print("\nAttempting to run 'kiro --help' in WSL...")
    
    # Test 1: Try with run_in_wsl
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
            
        # Check for model option
        import re
        m = re.search(r"--model\b[^(]*\(choices:\s*([^)]+)\)", stdout, re.DOTALL)
        if m:
            print("\n   ✓ Found model option in help!")
            choices_text = m.group(1)
            quoted_models = re.findall(r'"([^"]+)"', choices_text)
            print(f"   Models found: {quoted_models}")
        else:
            print("\n   ✗ Could not find model option in help")
            
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 2: Try direct execution (fallback)
    print("\n2. Direct execution (fallback):")
    try:
        from src.aicodereviewer.backends.models import _run_quiet
        rc, stdout, stderr = _run_quiet(["kiro", "--help"], timeout=5)
        print(f"   Return code: {rc}")
        print(f"   Stdout length: {len(stdout)} chars")
        if stderr:
            print(f"   Stderr: {stderr[:200]}")
            
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        
else:
    print("\nNot on Windows, skipping WSL tests")
