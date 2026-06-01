#!/usr/bin/env python3
"""Read-only Webull Trading API smoke test.

Loads ``WEBULL_APP_KEY`` / ``WEBULL_APP_SECRET`` from the normal runtime config,
lists accessible accounts, then optionally reads balance and positions for the
selected account. It never places, previews, or cancels orders.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Webull Trading API smoke test")
    parser.add_argument("--account-id", default=os.getenv("WEBULL_ACCOUNT_ID", ""))
    parser.add_argument("--skip-account", action="store_true")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Dump the raw, unparsed Webull JSON for balance/positions (field-name discovery).",
    )
    parser.add_argument(
        "--preview",
        metavar="SYMBOL",
        help="Validate the order path WITHOUT placing: resolve the instrument and "
        "call preview_order for SYMBOL (use --qty / --side). No order is submitted.",
    )
    parser.add_argument("--qty", type=float, default=1.0)
    parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    args = parser.parse_args()

    import tradingagents  # noqa: F401 - loads .env via package init

    from tradingbot.config import TRADINGBOT_CONFIG
    from tradingbot.broker.webull_client import SdkWebullClient

    app_key = str(TRADINGBOT_CONFIG.get("webull_app_key", "")).strip()
    app_secret = str(TRADINGBOT_CONFIG.get("webull_app_secret", "")).strip()
    if not app_key or not app_secret:
        print("WEBULL_APP_KEY and WEBULL_APP_SECRET are required", file=sys.stderr)
        return 2

    region = str(TRADINGBOT_CONFIG.get("webull_region", "us") or "us")
    paper = bool(TRADINGBOT_CONFIG.get("paper_trading", True))
    endpoint = str(TRADINGBOT_CONFIG.get("webull_endpoint", "") or "") or None
    client = SdkWebullClient(
        access_token="",
        app_key=app_key,
        app_secret=app_secret,
        auth_type="api_key",
        region=region,
        paper=paper,
        endpoint=endpoint,
        connect_timeout=float(TRADINGBOT_CONFIG.get("webull_connect_timeout", 10) or 10),
        read_timeout=float(TRADINGBOT_CONFIG.get("webull_read_timeout", 30) or 30),
    )

    health = client.health()
    print(_json({"step": "health", **health}))
    if not health.get("connected"):
        return 1

    accounts = [str(a) for a in health.get("accounts") or [] if a]
    account_id = args.account_id.strip() or (accounts[0] if len(accounts) == 1 else "")
    if args.skip_account:
        return 0
    if not account_id:
        print(
            "Multiple or zero accounts returned; rerun with --account-id <ACCOUNT_ID>",
            file=sys.stderr,
        )
        return 2

    if args.raw:
        # Bypass the normalisation layer and print exactly what Webull returns,
        # so we can reconcile field names against the live response.
        from tradingbot.broker.webull_client import _payload

        trade, _ = client._clients()  # noqa: SLF001 - debug-only access
        account_api = getattr(trade, "account_v2", trade)
        print(_json({"step": "raw_balance", "body": _payload(account_api.get_account_balance(account_id))}))
        get_pos = getattr(account_api, "get_account_position", None) or getattr(
            account_api, "get_account_positions"
        )
        print(_json({"step": "raw_positions", "body": _payload(get_pos(account_id))}))

    print(_json({"step": "balance", "account_id": account_id, **client.account_balance(account_id)}))
    positions = client.positions(account_id)
    print(_json({"step": "positions", "account_id": account_id, "count": len(positions)}))
    if positions:
        print(_json({"step": "positions_sample", "items": positions[:5]}))

    if args.preview:
        # Exercises the full order path (instrument resolution + payload + the
        # SDK "category" header) but stops at preview — nothing is submitted.
        from tradingbot.broker.webull import WebullBroker, OrderSide

        broker = WebullBroker(client, account_id=account_id, region=region, paper=paper)
        side = OrderSide.BUY if args.side == "buy" else OrderSide.SELL
        instrument_id = broker._instrument_id(args.preview)  # noqa: SLF001 - debug
        print(_json({"step": "resolve_instrument", "symbol": args.preview, "instrument_id": instrument_id}))
        preview = broker.preview_order(args.preview, args.qty, side)
        print(_json({"step": "preview_order", "symbol": args.preview, "qty": args.qty, **preview}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
