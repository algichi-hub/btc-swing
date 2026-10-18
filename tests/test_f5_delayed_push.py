"""F6 regression: temporary F5 delayed Push is removed from release candidate."""
from pathlib import Path
from app.notifications import push_api,cloud_dispatcher

def test_delayed_push_retired():
    assert not hasattr(push_api,"schedule_delayed_push")
    assert not Path("app/notifications/delayed_test.py").exists()
    assert "/test-delayed" not in Path("app/notifications/push_api.py").read_text()
    assert "drain_delayed_tests" not in Path("app/notifications/cloud_dispatcher.py").read_text()
    assert "Enviar Push en 30 segundos" not in Path("app/static/pwa-install.js").read_text()
