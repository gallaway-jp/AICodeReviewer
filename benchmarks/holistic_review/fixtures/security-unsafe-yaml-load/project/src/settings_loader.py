import yaml


def parse_settings_payload(raw_config: str):
    return yaml.load(raw_config, Loader=yaml.Loader)