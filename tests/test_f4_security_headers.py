"""F4 R06/R10/R19: regressions against committed Vercel security controls."""
import json
from pathlib import Path

def test_private_html_never_cached_and_api_no_store():
    v=json.loads(Path("app/static/vercel.json").read_text())
    routes={entry["source"]: {h["key"].lower():h["value"] for h in entry["headers"]} for entry in v["headers"]}
    assert "no-store" in routes["/(|index.html|login|login.html|ops|ops.html)"]["cache-control"]
    assert "no-store" in routes["/api/(.*)"]["cache-control"]
    assert "Cache-Control" not in str(v["rewrites"])

def test_restrictive_csp_and_headers():
    v=json.loads(Path("app/static/vercel.json").read_text())
    root={h["key"]:h["value"] for h in next(x for x in v["headers"] if x["source"]=="/(.*)")["headers"]}
    csp=root["Content-Security-Policy"]
    for rule in ["default-src 'self'", "object-src 'none'", "base-uri 'none'", "frame-ancestors 'none'", "script-src 'self'", "connect-src 'self'"]:
        assert rule in csp
    assert "'unsafe-eval'" not in csp
    assert "script-src 'self' 'unsafe-inline'" not in csp
    assert root["X-Frame-Options"] == "DENY"
    assert root["X-Content-Type-Options"] == "nosniff"

def test_no_inline_scripts_or_event_handlers_in_html():
    import re
    for path in Path("app/static").glob("*.html"):
        html=path.read_text()
        assert not re.search(r"<script\b(?![^>]*\bsrc\s*=)",html,re.I),path
        assert not re.search(r"\bon(?:click|load|error|submit|mouseover)\s*=",html,re.I),path

def test_no_dynamic_innerhtml_in_relevant_scripts():
    import re
    for path in ["app/static/app.js","app/static/ops.js","app/static/login.js"]:
        assert not re.search(r"\.innerHTML\s*=",Path(path).read_text()),path
