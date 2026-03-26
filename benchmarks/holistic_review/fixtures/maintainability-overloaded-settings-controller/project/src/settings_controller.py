import json
from datetime import datetime


class SettingsController:
    def __init__(self, repository, sync_service, telemetry, logger):
        self.repository = repository
        self.sync_service = sync_service
        self.telemetry = telemetry
        self.logger = logger

    def load_settings(self):
        raw_settings = self.repository.read_settings()
        if not raw_settings:
            raw_settings = {"sync_enabled": True, "sync_interval_minutes": 15, "timezone": "UTC"}

        if raw_settings.get("timezone") == "US/Pacific":
            raw_settings["timezone"] = "America/Los_Angeles"

        raw_settings["sync_interval_minutes"] = int(raw_settings.get("sync_interval_minutes", 15))
        return raw_settings

    def save_settings(self, form_values, current_user):
        normalized = {
            "sync_enabled": bool(form_values.get("sync_enabled", False)),
            "sync_interval_minutes": int(form_values.get("sync_interval_minutes", 15)),
            "timezone": form_values.get("timezone") or "UTC",
            "notify_email": (form_values.get("notify_email") or "").strip(),
        }

        if normalized["sync_interval_minutes"] < 5:
            normalized["sync_interval_minutes"] = 5
        if normalized["timezone"] == "US/Pacific":
            normalized["timezone"] = "America/Los_Angeles"
        if normalized["notify_email"] and "@" not in normalized["notify_email"]:
            raise ValueError("notify_email must be a valid address")

        existing = self.repository.read_settings()
        changes = []
        for key, new_value in normalized.items():
            if existing.get(key) != new_value:
                changes.append(f"{key}={new_value}")

        audit_entry = {
            "user": current_user,
            "changed_at": datetime.utcnow().isoformat(),
            "changes": changes,
        }
        self.repository.write_settings(normalized)
        self.repository.append_audit_log(audit_entry)

        if normalized["sync_enabled"]:
            self.sync_service.schedule_next_run(normalized["sync_interval_minutes"], normalized["timezone"])
            self.sync_service.refresh_remote_state()
        else:
            self.sync_service.cancel_pending_runs()

        self.telemetry.track(
            "settings_saved",
            {
                "sync_enabled": normalized["sync_enabled"],
                "sync_interval_minutes": normalized["sync_interval_minutes"],
                "timezone": normalized["timezone"],
            },
        )
        self.logger.info("Saved settings for %s: %s", current_user, ",".join(changes))

        return self.build_summary(normalized, audit_entry)

    def export_debug_snapshot(self):
        payload = {
            "settings": self.repository.read_settings(),
            "audit_log": self.repository.read_audit_log(),
        }
        return json.dumps(payload, indent=2, sort_keys=True)

    def build_summary(self, settings, audit_entry):
        enabled_label = "Enabled" if settings["sync_enabled"] else "Disabled"
        email_label = settings["notify_email"] or "No notification email"
        changed_fields = ", ".join(audit_entry["changes"]) or "No changes"
        return (
            f"Sync: {enabled_label}\n"
            f"Interval: {settings['sync_interval_minutes']} minutes\n"
            f"Timezone: {settings['timezone']}\n"
            f"Notifications: {email_label}\n"
            f"Changes: {changed_fields}"
        )
