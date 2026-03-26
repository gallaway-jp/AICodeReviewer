import pytest

from src.api import create_rollout


def test_create_rollout_returns_batch_size_for_valid_payload() -> None:
    result = create_rollout({"target_hosts": "25", "rollout_percent": "40"})

    assert result == {"status": "scheduled", "batch_size": 10}


def test_create_rollout_rejects_missing_rollout_percent() -> None:
    with pytest.raises(ValueError, match="rollout_percent"):
        create_rollout({"target_hosts": "25"})