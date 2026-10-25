from pathlib import Path


def test_manual_polling_is_two_seconds_and_three_minutes_max():
    source = Path("app/static/app.js").read_text()
    assert "for (let attempt = 0; attempt < 90; attempt++)" in source
    assert "window.setTimeout(resolve, 2000)" in source
    assert "window.setTimeout(resolve, 5000)" not in source[source.index("const { id } = await enqueued.json()"):source.index("if (!finished) throw new Error")]


def test_manual_completion_requires_matching_persisted_snapshot():
    source = Path("app/static/app.js").read_text()
    assert "state.status !== 'OK'" in source
    assert "Date.parse(lastDisplayedSnapshotAt) === Date.parse(state.snapshot_at)" in source
    assert "refreshDashboard({ scheduleNext: true })" in source
