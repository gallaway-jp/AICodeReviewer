from src.validation import validate_workflow


def create_workflow(payload: dict) -> dict:
    validate_workflow(payload)
    return {
        "status": "scheduled",
        "delivery_mode": payload["delivery_mode"],
    }