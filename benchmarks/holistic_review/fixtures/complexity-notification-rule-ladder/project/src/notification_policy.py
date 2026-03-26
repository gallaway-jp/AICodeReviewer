def plan_notification_delivery(event, recipient, policy, now_hour):
    channel = "email"
    priority = "normal"
    send_now = True

    if event["kind"] == "security":
        priority = "critical"
        if recipient["is_vip"]:
            channel = "phone"
        elif recipient["prefers_sms"]:
            channel = "sms"
        else:
            channel = "email"
    elif event["kind"] == "billing":
        if recipient["account_tier"] == "enterprise":
            channel = "email"
            priority = "high"
        elif recipient["prefers_sms"] and event["amount_due"] > 500:
            channel = "sms"
            priority = "high"
        else:
            channel = "email"
    elif event["kind"] == "digest":
        channel = "email"
        priority = "low"
        send_now = False
    else:
        if recipient["prefers_push"]:
            channel = "push"
        else:
            channel = "email"

    if policy["quiet_hours_enabled"]:
        if now_hour >= policy["quiet_hours_start"] or now_hour < policy["quiet_hours_end"]:
            if priority == "critical":
                if recipient["allow_night_escalation"]:
                    channel = "phone"
                    send_now = True
                else:
                    channel = "sms"
            elif channel == "sms":
                if recipient["account_tier"] == "enterprise":
                    send_now = True
                else:
                    send_now = False
            elif channel == "push":
                if event["kind"] == "billing":
                    send_now = True
                else:
                    send_now = False
            else:
                send_now = False

    if policy["compliance_mode"]:
        if event["contains_pii"]:
            if channel == "push":
                channel = "email"
            elif channel == "sms":
                if recipient["account_tier"] == "enterprise":
                    channel = "email"
                else:
                    send_now = False
        if event["kind"] == "security" and recipient["region"] == "eu":
            channel = "email"

    if recipient["account_tier"] == "free":
        if event["kind"] == "digest":
            send_now = False
        elif priority == "critical":
            channel = "email"
        elif channel == "phone":
            channel = "sms"

    return {
        "channel": channel,
        "priority": priority,
        "send_now": send_now,
    }