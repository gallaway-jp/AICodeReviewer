def describe_export(export_path: str) -> str:
    path_parts = export_path.split("/")
    export_name = path_parts[-1]
    account_id = path_parts[-3]
    return f"{account_id}:{export_name}"