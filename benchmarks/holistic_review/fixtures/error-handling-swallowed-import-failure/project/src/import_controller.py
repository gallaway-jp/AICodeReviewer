from .import_job import run_import


def import_customers(upload: str) -> dict[str, object]:
    result = run_import(upload)
    if result["status"] == "completed":
        return {"message": "Import finished", "imported": result["count"]}
    return {"message": "Import failed"}