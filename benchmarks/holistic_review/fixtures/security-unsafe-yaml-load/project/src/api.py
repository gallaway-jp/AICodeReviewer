from .settings_loader import parse_settings_payload


def import_settings(request: dict[str, str]):
    raw_config = request["config"]
    return parse_settings_payload(raw_config)