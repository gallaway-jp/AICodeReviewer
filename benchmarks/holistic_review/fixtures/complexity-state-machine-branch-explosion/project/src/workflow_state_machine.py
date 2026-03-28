def advance_workflow_state(workflow, event, retry_mode, feature_flags):
    next_state = workflow["state"]
    notify = False
    persist_checkpoint = False

    if workflow["state"] == "draft":
        if event == "submit":
            if feature_flags.get("require_review"):
                if workflow["owner_is_admin"]:
                    next_state = "queued"
                    persist_checkpoint = True
                else:
                    next_state = "pending_review"
            else:
                if feature_flags.get("allow_direct_start"):
                    next_state = "running"
                    notify = True
                else:
                    next_state = "queued"
        elif event == "cancel":
            next_state = "cancelled"
        else:
            next_state = "draft"

    elif workflow["state"] == "queued":
        if event == "dispatch":
            if workflow["has_capacity"]:
                if retry_mode == "resume":
                    next_state = "running"
                    persist_checkpoint = True
                else:
                    if feature_flags.get("warm_start"):
                        next_state = "warming"
                    else:
                        next_state = "running"
            else:
                if feature_flags.get("overflow_pause"):
                    next_state = "paused"
                else:
                    next_state = "queued"
        elif event == "cancel":
            next_state = "cancelled"

    elif workflow["state"] == "running":
        if event == "success":
            if workflow["requires_audit"]:
                next_state = "awaiting_audit"
            else:
                next_state = "completed"
                notify = True
        elif event == "failure":
            if retry_mode == "auto":
                if workflow["attempt_count"] < 3:
                    next_state = "queued"
                    persist_checkpoint = True
                else:
                    next_state = "failed"
                    notify = True
            else:
                if feature_flags.get("pause_on_manual_retry"):
                    next_state = "paused"
                else:
                    next_state = "failed"
        elif event == "pause":
            next_state = "paused"

    elif workflow["state"] == "paused":
        if event == "resume":
            if workflow["has_capacity"]:
                if feature_flags.get("resume_to_review") and workflow["requires_audit"]:
                    next_state = "awaiting_audit"
                else:
                    next_state = "queued"
            else:
                next_state = "paused"
        elif event == "cancel":
            next_state = "cancelled"

    elif workflow["state"] == "failed":
        if event == "retry":
            if workflow["attempt_count"] < 5:
                if feature_flags.get("retry_from_pause"):
                    next_state = "paused"
                else:
                    next_state = "queued"
                    persist_checkpoint = True
            else:
                next_state = "failed"
        elif event == "archive":
            next_state = "archived"

    return {
        "state": next_state,
        "notify": notify,
        "persist_checkpoint": persist_checkpoint,
    }