import os
import json
import subprocess
import sys
from pathlib import Path

OUTPUT_DIR = Path("licenses")


def _pip_licenses_command() -> list[str]:
    scripts_dir = Path(sys.executable).resolve().parent
    executable_names = ["pip-licenses.exe", "pip-licenses"] if os.name == "nt" else ["pip-licenses"]
    for executable_name in executable_names:
        candidate = scripts_dir / executable_name
        if candidate.exists():
            return [str(candidate)]
    return ["pip-licenses"]


def ensure_output_dir():
    OUTPUT_DIR.mkdir(exist_ok=True)


def run_pip_licenses_json():
    cmd = [
        *_pip_licenses_command(),
        "--from=mixed",
        "--format=json",
        "--with-license-file",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"pip-licenses failed: {result.stderr}")
    return json.loads(result.stdout)


def read_license_text(entry):
    # Try reading from LicenseFile path provided by pip-licenses
    license_file = entry.get("LicenseFile") or entry.get("license_file")
    if license_file and os.path.exists(license_file):
        try:
            with open(license_file, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception:
            pass
    # Fall back to provided License string
    return entry.get("License") or entry.get("license")


def write_individual_license_files(entries):
    for entry in entries:
        name = entry.get("Name") or entry.get("name")
        text = read_license_text(entry)
        if not name:
            # skip entries without a name
            continue
        filename = OUTPUT_DIR / f"{name}-LICENSE.txt"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(str(text) if text else "")
        except Exception as e:
            print(f"Warning: Failed writing {filename}: {e}")


def write_combined_markdown(entries):
    md_file = OUTPUT_DIR / "LICENSES.md"
    with open(md_file, "w", encoding="utf-8") as f:
        f.write("# Third-Party Licenses\n\n")
        for entry in entries:
            name = entry.get("Name") or entry.get("name")
            version = entry.get("Version") or entry.get("version")
            license_name = entry.get("License") or entry.get("license")
            license_text = read_license_text(entry)
            f.write(f"## {name} {version} — {license_name}\n\n")
            if license_text:
                f.write(f"````\n{license_text}\n````\n\n")
            else:
                f.write("(No license text available from pip-licenses)\n\n")


def main():
    ensure_output_dir()
    pip_licenses_cmd = _pip_licenses_command()

    # Ensure pip-licenses is available
    try:
        subprocess.run([*pip_licenses_cmd, "--version"], capture_output=True, text=True, check=True)
    except Exception:
        print("Installing pip-licenses...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pip-licenses"], check=True)

    print("Collecting license information...")
    entries = run_pip_licenses_json()

    print("Writing individual license files...")
    write_individual_license_files(entries)

    print("Writing combined markdown report...")
    write_combined_markdown(entries)

    print(f"Done. Licenses written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
