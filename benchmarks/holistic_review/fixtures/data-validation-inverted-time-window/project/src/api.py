from src.validation import validate_window


def create_maintenance_window(payload: dict) -> dict:
    validate_window(payload)
    duration_hours = int(payload["end_hour"]) - int(payload["start_hour"])
    return {
        "status": "scheduled",
        "duration_hours": duration_hours,
    }