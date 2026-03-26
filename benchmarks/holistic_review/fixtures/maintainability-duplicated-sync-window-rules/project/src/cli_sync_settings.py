def normalize_sync_window(payload):
    start_hour = payload.get("start_hour", "09")
    end_hour = payload.get("end_hour", "17")
    allow_weekends = payload.get("allow_weekends", False)
    timezone = payload.get("timezone") or "UTC"

    start_hour = str(start_hour).strip()
    end_hour = str(end_hour).strip()

    if len(start_hour) == 1:
        start_hour = f"0{start_hour}"
    if len(end_hour) == 1:
        end_hour = f"0{end_hour}"

    if start_hour == "24":
        start_hour = "00"
    if end_hour == "24":
        end_hour = "00"

    normalized = {
        "start_hour": start_hour,
        "end_hour": end_hour,
        "allow_weekends": bool(allow_weekends),
        "timezone": timezone,
    }

    if normalized["start_hour"] == normalized["end_hour"]:
        normalized["end_hour"] = "18"

    if normalized["timezone"] == "US/Pacific":
        normalized["timezone"] = "America/Los_Angeles"

    return normalized
