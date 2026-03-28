def parse_sync_selector(raw_selector):
    selector = (raw_selector or "").strip()
    parsed = {"projects": [], "labels": [], "all_projects": False}

    if not selector or selector == "*":
        parsed["all_projects"] = True
        return parsed

    for chunk in selector.split(","):
        token = chunk.strip()
        if not token:
            continue

        key, value = token.split("=", 1)
        key = key.strip().lower()
        value = value.strip().lower()

        if key == "project":
            parsed["projects"].append(value)
        elif key in {"label", "tag"}:
            parsed["labels"].append(value)
        elif key == "all":
            parsed["all_projects"] = value in {"1", "true", "yes"}
        else:
            raise ValueError(f"Unsupported selector token: {token}")

    return parsed