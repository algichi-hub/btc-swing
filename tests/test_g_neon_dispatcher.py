"""G-NEON regression: dispatcher cadence is bounded and independent of Engine."""
import os
from unittest.mock import patch
import pytest

from app.notifications.cloud_dispatcher import polling_seconds
from app.automation.cloud_worker import INTERVAL_SECONDS


def test_default_push_poll_does_not_change_engine():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("PUSH_POLL_SECONDS", None)
        assert polling_seconds() == 30
        assert INTERVAL_SECONDS == 300


@pytest.mark.parametrize("seconds", ["5", "30", "300"])
def test_push_poll_valid(seconds):
    with patch.dict(os.environ, {"PUSH_POLL_SECONDS": seconds}):
        assert polling_seconds() == int(seconds)


@pytest.mark.parametrize("seconds", ["0", "4", "301", "-1", "nan", "1.5"])
def test_push_poll_rejects_invalid(seconds):
    with patch.dict(os.environ, {"PUSH_POLL_SECONDS": seconds}):
        with pytest.raises(ValueError):
            polling_seconds()
