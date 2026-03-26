import subprocess


def run_export(*, username: str, output_format: str, output_path: str) -> bool:
    command = (
        f"generate-report --user {username} --format {output_format} --output {output_path}"
    )
    completed = subprocess.run(
        command,
        shell=True,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0