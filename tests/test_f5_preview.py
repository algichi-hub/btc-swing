"""F5 safety gates for non-operational preparation."""
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
import pytest
from app.notifications.push_outbox import SimulatedOutbox

ROOT=Path("app/static")
def test_manifest_scoped_login_not_private_cache():
    m=json.loads((ROOT/"manifest.webmanifest").read_text())
    assert m["scope"]=="/" and m["start_url"]=="/login" and m["display"]=="standalone"
    assert m["icons"] and m["id"]=="/"
    assert {icon["sizes"] for icon in m["icons"]} >= {"192x192","512x512"}
    for n in (192,512):
        raw=(ROOT/f"icon-{n}.png").read_bytes()
        assert raw[:8]==bytes.fromhex("89504e470d0a1a0a")
        assert int.from_bytes(raw[16:20],"big")==n
    for p in ("login.html","index.html"):
        page=(ROOT/p).read_text()
        assert 'rel="manifest"' in page
        assert '/static/pwa-install.js' in page
def test_worker_never_caches_private_data():
    text=(ROOT/"sw.js").read_text()
    assert "caches.delete(key)" in text
    assert "Cache.put" in text and "no persistent storage" in text
    assert "cache.put(" not in text.lower()
    assert "BTC_V5_TEST" in text
    assert "self.clients.openWindow('/login')" in text
def test_idempotency_and_replay():
    o=SimulatedOutbox()
    x=o.enqueue("cycle-123","TEST",{"kind":"BTC_V5_TEST"})
    y=o.enqueue("cycle-123","TEST",{"kind":"BTC_V5_TEST"})
    assert x is y and len(o.events)==1
    assert o.dispatch_simulated(lambda _:True)==1
    assert o.dispatch_simulated(lambda _:True)==0
    assert x.attempts==1
def test_retries_and_ttl():
    o=SimulatedOutbox()
    x=o.enqueue("1","TEST",{"kind":"BTC_V5_TEST"},ttl_seconds=10)
    assert o.dispatch_simulated(lambda _:False)==0 and x.attempts==1
    assert o.dispatch_simulated(lambda _:True, x.expires_at+timedelta(seconds=1))==0
    assert x.attempts==1 and not x.delivered
def test_reject_sensitive_payload():
    with pytest.raises(ValueError):
        SimulatedOutbox().enqueue("a","TEST",{"wallet":"secret"})


def test_worker_root_scope_has_real_file_not_self_rewrite():
    v=json.loads((ROOT/"vercel.json").read_text())
    assert not any(r["source"]=="/sw.js" for r in v["rewrites"])
    assert "navigator.serviceWorker.register('/sw.js'" in (ROOT/"pwa-install.js").read_text()
