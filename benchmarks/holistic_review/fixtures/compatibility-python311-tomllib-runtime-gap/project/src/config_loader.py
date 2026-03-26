import tomllib


def load_settings(config_path):
    with open(config_path, "rb") as config_file:
        return tomllib.load(config_file)
