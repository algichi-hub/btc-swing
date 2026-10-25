"""Manual dashboard recalculation cannot persist setups or mutate Engine context."""
from pathlib import Path
from app.strategy.setup_context import SetupContextManager


def test_manual_refresh_uses_isolated_nonpersistent_manager():
    source = Path("app/main.py").read_text()
    assert "def build_dashboard_payload(*, read_only: bool = False)" in source
    assert "SetupContextManager(repository=None) if read_only else setup_context_manager" in source
    assert "build_dashboard_payload(read_only=True)" in source
    assert "manual_refresh_read_only" in source


def test_isolated_manager_has_no_repository_or_shared_state():
    runtime = SetupContextManager(repository=object())
    manual = SetupContextManager(repository=None)
    assert runtime is not manual
    assert runtime.repository is not None
    assert manual.repository is None
    assert manual.current_setup is None
