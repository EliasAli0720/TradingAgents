"""Phase 0 connectivity smoke for the IBKR TWS API integration.

Verifies that a locally running TWS (or IB Gateway) is reachable over the
socket API and that we can read the account before any adapter code exists.
It is strictly READ-ONLY: it connects, prints the account summary, resolves
one stock to its conid, and pulls one (delayed by default) quote. It never
places, previews, or cancels an order.

Run this once your TWS/Gateway is logged in (paper recommended) and the API
is enabled (Global Configuration -> API -> Settings -> Enable ActiveX and
Socket Clients). See docs/superpowers/specs/2026-05-29-ibkr-tws-api-integration-design.md

Usage:
    pip install ib_async
    python scripts/ibkr_smoke.py                 # paper TWS on 127.0.0.1:7497
    python scripts/ibkr_smoke.py --symbol NVDA
    python scripts/ibkr_smoke.py --port 4002     # paper IB Gateway
    IBKR_PORT=7497 IBKR_CLIENT_ID=11 python scripts/ibkr_smoke.py

Default port 7497 = paper TWS. Other defaults: 7496 live TWS, 4002 paper
Gateway, 4001 live Gateway. clientId defaults to 11 (a dev id) so it never
clashes with the production Connector's master clientId=0.
"""

from __future__ import annotations

import argparse
import math
import os
import sys

# Ports that talk to REAL money — we warn loudly before connecting.
_LIVE_PORTS = {7496, 4001}

# Account-summary tags we map onto the system's AccountInfo model.
_SUMMARY_TAGS = "NetLiquidation,AvailableFunds,BuyingPower,TotalCashValue"


def _pick_price(ticker) -> float | None:
    """Best-effort price: last -> midpoint(bid,ask) -> close. None if nothing."""

    def ok(v) -> bool:
        return v is not None and not (isinstance(v, float) and math.isnan(v))

    if ok(ticker.last):
        return float(ticker.last)
    if ok(ticker.bid) and ok(ticker.ask):
        return (float(ticker.bid) + float(ticker.ask)) / 2.0
    if ok(ticker.close):
        return float(ticker.close)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="IBKR TWS API connectivity smoke (read-only).")
    parser.add_argument("--host", default=os.getenv("IBKR_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("IBKR_PORT", "7497")))
    parser.add_argument("--client-id", type=int, default=int(os.getenv("IBKR_CLIENT_ID", "11")))
    parser.add_argument("--symbol", default=os.getenv("IBKR_SMOKE_SYMBOL", "AAPL"))
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    try:
        from ib_async import IB, Stock
    except ImportError:
        print("ib_async is required. Install it with: pip install ib_async", file=sys.stderr)
        return 1

    if args.port in _LIVE_PORTS:
        print(f"\n  ⚠️  Port {args.port} is a LIVE (real-money) port. This smoke is read-only,")
        print("      but you should verify against a PAPER account (7497 TWS / 4002 Gateway).\n")

    ib = IB()
    print(f"Connecting to {args.host}:{args.port} (clientId={args.client_id}) ...")
    try:
        ib.connect(args.host, args.port, clientId=args.client_id, timeout=args.timeout)
    except Exception as exc:  # noqa: BLE001 - smoke script, surface the raw cause
        print(f"\n  ✗ Could not connect: {exc}\n", file=sys.stderr)
        print("  Checklist:", file=sys.stderr)
        print("   - TWS/Gateway logged in?", file=sys.stderr)
        print("   - API enabled? (Global Configuration -> API -> Settings -> Enable ActiveX and Socket Clients)", file=sys.stderr)
        print(f"   - Socket port matches --port {args.port}?", file=sys.stderr)
        print("   - Accept the 'incoming connection' popup in TWS, or trust 127.0.0.1.", file=sys.stderr)
        return 1

    try:
        print(f"  ✓ Connected. Server version: {ib.client.serverVersion()}")

        accounts = ib.managedAccounts()
        print(f"  Managed accounts: {accounts or '(none)'}")
        if accounts:
            paper_hint = " (paper)" if accounts[0].startswith("DU") else " (LIVE?)"
            print(f"  Primary account: {accounts[0]}{paper_hint}")

        print("\nAccount summary:")
        summary = ib.accountSummary()  # all accounts; tags filtered below
        wanted = set(_SUMMARY_TAGS.split(","))
        rows = [v for v in summary if v.tag in wanted]
        if not rows:
            print("  (no summary returned — is this account funded / a paper account?)")
        for v in rows:
            print(f"  {v.tag:<16} {v.value:>16} {v.currency}")

        print(f"\nResolving contract for {args.symbol} ...")
        contracts = ib.qualifyContracts(Stock(args.symbol, "SMART", "USD"))
        if not contracts:
            print(f"  ✗ Could not qualify {args.symbol}")
            return 1
        contract = contracts[0]
        print(f"  ✓ {args.symbol} -> conid={contract.conId} exchange={contract.primaryExchange or contract.exchange}")

        print("\nRequesting a quote (delayed) ...")
        ib.reqMarketDataType(3)  # 3 = delayed, no real-time subscription needed
        ticker = ib.reqMktData(contract, "", False, False)
        ib.sleep(2.5)  # let ticks arrive
        price = _pick_price(ticker)
        ib.cancelMktData(contract)
        if price is None:
            print("  (no price yet — delayed data can lag; outside market hours 'close' may be empty)")
        else:
            print(f"  {args.symbol} ~ {price:.2f}  (last={ticker.last} bid={ticker.bid} ask={ticker.ask} close={ticker.close})")

        print("\n  ✓ Smoke passed — TWS API connectivity is working.\n")
        return 0
    finally:
        ib.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
