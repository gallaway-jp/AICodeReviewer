import subprocess


def open_exported_report(report_path):
    subprocess.run(["open", report_path], check=True)
