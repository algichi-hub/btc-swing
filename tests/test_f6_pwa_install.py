from io import BytesIO
import struct
from pathlib import Path
from fastapi.testclient import TestClient
from app.pwa_assets import icon_png
from app.main import create_app

def test_real_png_icon_sizes():
    for size in (192, 512):
        data=icon_png(size)
        assert data[:8] == bytes.fromhex("89504e470d0a1a0a")
        assert struct.unpack(">II",data[16:24])==(size,size)

def test_pwa_assets_publicly_available():
    app=create_app()
    client=TestClient(app,follow_redirects=False)
    response=client.get("/sw.js")
    assert response.status_code==200
    assert "javascript" in response.headers["content-type"]
    assert "self.addEventListener('push'" in response.text
    for size in (192,512):
        r=client.get(f"/pwa/icon-{size}.png")
        assert r.status_code==200
        assert r.headers["content-type"].startswith("image/png")

def test_manifest_references_real_png_and_home():
    import json
    data=json.loads(Path("app/static/manifest.webmanifest").read_text())
    assert data["start_url"]=="/login"
    assert data["scope"]=="/"
    assert data["display"]=="standalone"
    assert {i["src"] for i in data["icons"]} >= {"/pwa/icon-192.png","/pwa/icon-512.png"}
