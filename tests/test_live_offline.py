"""The live page with Blender's Allow Online Access off (bpy.app.online_access,
lib/monitoring/live.py online()): the page still served on this machine,
never on the network -- no access made for a phone, the running ones kept
but their network server closed, back once it's on again.

    python3 tests/test_live_offline.py
"""

import importlib
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    live = importlib.import_module(f"{pkg.__name__}.lib.monitoring.live")
    bpy = sys.modules["bpy"]

    # Without the property (an older Blender, the fake): online.
    if hasattr(bpy.app, "online_access"):
        delattr(bpy.app, "online_access")
    assert live.online() is True

    with tempfile.TemporaryDirectory() as d:
        sh = live._Shared(Path(d), "token")
        live._save_guests = lambda: None
        live._addresses = lambda: [{"ip": "192.168.1.20", "kind": "local network"}]

        class Server:
            server_address = ("127.0.0.1", 8765)
            closed = False

            def shutdown(self):
                pass

            def server_close(self):
                self.closed = True

        live._server = Server()

        bpy.app.online_access = False
        assert live.online() is False

        # No access made: said why, the list still given (to revoke one).
        out = live._share({"name": "Ana", "role": "team", "hours": 1}, sh)
        assert out["ok"] is False and out["error"] == live.OFFLINE and out["online"] is False, out
        assert not live._guests and not live._lan["servers"]
        out = live._share({}, sh)
        assert out["ok"] is True and out["online"] is False, out

        # One made while it was on: kept, its network server closed.
        lan = Server()
        live._lan["servers"]["192.168.1.20"] = lan
        live._guests["tok"] = {"name": "Ana", "role": "team", "until": time.time() + 3600, "ip": "192.168.1.20"}
        live._sync_lan(sh)
        assert lan.closed and not live._lan["servers"], live._lan
        assert "tok" in live._guests

        # Back on: it would be served again (a real server needs a real address: not opened here).
        bpy.app.online_access = True
        assert live.online() is True
        assert live._share({}, sh)["online"] is True
        live._guests.clear()
        live._server = None
    print("test_live_offline: ok")


if __name__ == "__main__":
    main()
