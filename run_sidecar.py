"""Entry point for the local broker sidecar.

Launched by the Electron desktop shell with a per-session token and a free
loopback port:

    python run_sidecar.py --host 127.0.0.1 --port 8788 --token <hex>

Binds 127.0.0.1 only. The token (also passed via the SIDECAR_TOKEN env var)
gates every endpoint except /ping. See
docs/superpowers/specs/2026-05-30-electron-desktop-local-broker-design.md
"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="TradingAgents local broker sidecar")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("SIDECAR_PORT", "8788")))
    parser.add_argument("--token", default=os.getenv("SIDECAR_TOKEN", ""))
    args = parser.parse_args()

    # The app reads SIDECAR_TOKEN at request time; make sure it is set.
    os.environ["SIDECAR_TOKEN"] = args.token

    import uvicorn

    # Import the app object directly (not the "module:app" string) so a frozen
    # PyInstaller bundle doesn't need to resolve the import path at runtime.
    from tradingbot.sidecar.app import app

    # Always loopback — never expose the trading port off-host.
    host = "127.0.0.1" if args.host not in ("127.0.0.1", "localhost") else args.host
    uvicorn.run(app, host=host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
