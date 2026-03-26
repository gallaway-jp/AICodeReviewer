def choose_sync_strategy(account, network_state, retry_mode, feature_flags):
    strategy = "defer"

    if account["is_active"]:
        if feature_flags.get("progressive_sync"):
            if network_state["is_metered"]:
                if retry_mode == "forced":
                    if account["has_pending_conflicts"]:
                        strategy = "metadata_only"
                    else:
                        if account["priority"] == "high":
                            strategy = "partial"
                        else:
                            strategy = "defer"
                else:
                    if network_state["latency_ms"] < 120:
                        strategy = "partial"
                    else:
                        if account["priority"] == "high":
                            strategy = "metadata_only"
                        else:
                            strategy = "defer"
            else:
                if account["has_pending_conflicts"]:
                    if retry_mode == "forced":
                        strategy = "full"
                    else:
                        if feature_flags.get("conflict_fast_path"):
                            strategy = "partial"
                        else:
                            strategy = "metadata_only"
                else:
                    if account["priority"] == "high":
                        if network_state["latency_ms"] < 200:
                            strategy = "full"
                        else:
                            strategy = "partial"
                    else:
                        if retry_mode == "scheduled":
                            strategy = "partial"
                        else:
                            strategy = "metadata_only"
        else:
            if retry_mode == "forced":
                strategy = "full"
            else:
                if network_state["is_metered"]:
                    strategy = "defer"
                else:
                    strategy = "partial"

    return strategy