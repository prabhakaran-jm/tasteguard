from starlette.routing import Mount
from fastapi.testclient import TestClient

from app.main import app
from app.mcp_server import mcp


def test_mcp_tools_registered():
    names = {t.name for t in mcp._tool_manager.list_tools()}
    assert names >= {
        "tasteguard_list_presets",
        "tasteguard_evaluate",
        "tasteguard_repair",
    }


def test_mcp_mounted_under_prefix():
    mounts = [r for r in app.routes if isinstance(r, Mount) and r.path == "/mcp"]
    assert len(mounts) == 1
    sub_paths = {getattr(r, "path", None) for r in mounts[0].routes}
    assert "/sse" in sub_paths


def test_api_still_reachable_with_mcp_mounted():
    client = TestClient(app)
    res = client.get("/api/health")
    assert res.status_code == 200
    assert "qloo_key" in res.json()
