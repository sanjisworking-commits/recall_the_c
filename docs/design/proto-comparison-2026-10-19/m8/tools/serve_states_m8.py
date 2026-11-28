"""M8-Ra: serve one account in one subscription state for browser capture.

The same seeding as `readback_m8.py` (its `STATES`, `apply_state`): a throwaway
SQLite database, the dev fake Google sign-in, the application's own save
points for the Playground content, then the subscription row turned into the
state. No payment provider is configured or called.

`--other-devices N` registers N other browsers on the account first (each a
separate signed-in session that opens the Playground), so the capture browser
is the one at or over the limit. Without it the tool's own device rows are
removed, so the capture session and one more are the account's two devices.

    PYTHONPATH=.:src .venv/bin/python …/m8/tools/serve_states_m8.py --port 8933 --state paused [--tier-model choices] [--other-devices 2]
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
import readback_m8 as rb  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8933)
    ap.add_argument("--state", default="paused", choices=sorted(rb.STATES))
    ap.add_argument("--tier-model", default="monthly")
    ap.add_argument("--other-devices", type=int, default=0)
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="m8-states-"))
    app = rb.make_app(tmp, args.tier_model)
    setup = TestClient(app)
    rb.sign_in(setup)
    app.state.engine.repo.upsert_profile(rb.USER, display_name="Sanjay", avatar_url=None)
    saves = rb.apply_state(setup, args.state)
    devices = getattr(app.state, "device_service", None)
    if devices is not None:
        conn = devices._repo._conn
        for table in ("user_device_session", "user_device_replacement", "user_device"):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    registered = 0
    for _ in range(args.other_devices):
        other = TestClient(app)
        rb.sign_in(other)
        other.get("/playground")
        registered += 1
    print(f"M8 state server ready on http://127.0.0.1:{args.port} state={args.state} reach={rb.STATES[args.state]['reach']} "
          f"model={args.tier_model} other_devices={registered} saves={saves}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
