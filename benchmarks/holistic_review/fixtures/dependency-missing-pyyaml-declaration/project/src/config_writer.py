import yaml


def write_config(destination, payload):
    with open(destination, "w", encoding="utf-8") as output_file:
        yaml.safe_dump(payload, output_file, sort_keys=True)
