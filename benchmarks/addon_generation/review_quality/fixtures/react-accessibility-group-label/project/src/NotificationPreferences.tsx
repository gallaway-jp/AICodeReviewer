type NotificationPreferencesProps = {
  emailEnabled: boolean;
  smsEnabled: boolean;
  digestFrequency: "daily" | "weekly";
  onToggleEmail: () => void;
  onToggleSms: () => void;
  onDigestChange: (value: "daily" | "weekly") => void;
};

export function NotificationPreferences({
  emailEnabled,
  smsEnabled,
  digestFrequency,
  onToggleEmail,
  onToggleSms,
  onDigestChange,
}: NotificationPreferencesProps) {
  return (
    <form className="notification-preferences">
      <fieldset className="channel-group">
        <p className="group-heading">Delivery channels</p>
        <label>
          <input type="checkbox" checked={emailEnabled} onChange={onToggleEmail} />
          Email updates
        </label>
        <label>
          <input type="checkbox" checked={smsEnabled} onChange={onToggleSms} />
          SMS alerts
        </label>
      </fieldset>

      <fieldset className="digest-group">
        <p className="group-heading">Digest frequency</p>
        <label>
          <input
            type="radio"
            name="digest-frequency"
            value="daily"
            checked={digestFrequency === "daily"}
            onChange={() => onDigestChange("daily")}
          />
          Daily
        </label>
        <label>
          <input
            type="radio"
            name="digest-frequency"
            value="weekly"
            checked={digestFrequency === "weekly"}
            onChange={() => onDigestChange("weekly")}
          />
          Weekly
        </label>
      </fieldset>
    </form>
  );
}