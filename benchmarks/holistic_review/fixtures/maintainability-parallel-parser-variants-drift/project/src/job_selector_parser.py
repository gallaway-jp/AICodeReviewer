def parse_sync_selector(raw_selector):
    selector = (raw_selector or "").strip()
    parsed = {"projects": [], "labels": [], "all_projects": False}

    if not selector:
        return parsed

    for chunk in selector.split(","):
        token = chunk.strip()
        if not token:
            continue

        key, value = token.split("=", 1)
        key = key.strip().lower()
        value = value.strip()

        if key == "project":
            parsed["projects"].append(value)
        elif key == "label":
            parsed["labels"].append(value)
        elif key == "all":
            parsed["all_projects"] = value == "true"
        else:
            raise ValueError(f"Unsupported selector token: {token}")

    return parsed