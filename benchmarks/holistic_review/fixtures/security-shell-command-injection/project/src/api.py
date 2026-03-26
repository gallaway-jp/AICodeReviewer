from .report_export import run_export


def export_activity_report(request: dict[str, str], current_user: dict[str, str]) -> dict[str, bool]:
    output_path = request["output_path"]
    output_format = request.get("format", "csv")

    return {
        "started": run_export(
            username=current_user["username"],
            output_format=output_format,
            output_path=output_path,
        )
    }