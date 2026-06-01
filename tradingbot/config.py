"""
TradingBot runtime configuration.

Edit this file (or override via environment variables) to customise
your watchlist, position sizing, broker selection, and risk limits.
"""

import os

TRADINGBOT_CONFIG = {
    # ------------------------------------------------------------------ #
    # Broker                                                               #
    # ------------------------------------------------------------------ #
    # "alpaca" → AlpacaBroker (requires ALPACA_API_KEY / ALPACA_API_SECRET)
    # "ibkr"   → IBKRBroker   (TWS API socket; needs a logged-in TWS / IB Gateway)
    # "mock"   → MockBroker   (no credentials needed, safe for testing)
    "broker": os.getenv("TRADINGBOT_BROKER", "mock"),

    # Broker-agnostic paper flag. Set to False ONLY when ready for live money.
    # Driven by IBKR_PAPER for the ibkr broker, else ALPACA_PAPER.
    "paper_trading": os.getenv(
        "IBKR_PAPER"
        if os.getenv("TRADINGBOT_BROKER", "mock").lower() == "ibkr"
        else "ALPACA_PAPER",
        "true",
    ).lower() != "false",

    "alpaca_api_key": os.getenv("ALPACA_API_KEY", ""),
    "alpaca_api_secret": os.getenv("ALPACA_API_SECRET", ""),

    # ------------------------------------------------------------------ #
    # IBKR (TWS API / socket route — single platform account)             #
    # ------------------------------------------------------------------ #
    # Connect to a logged-in TWS / IB Gateway on this host. Paper ports:
    # TWS 7497, IB Gateway 4002 (live: 7496 / 4001).
    "ibkr_host": os.getenv("IBKR_HOST", "127.0.0.1"),
    "ibkr_port": int(os.getenv("IBKR_PORT", "7497")),
    # The connector uses the master client id (0) to receive all order updates.
    "ibkr_client_id": int(os.getenv("IBKR_CLIENT_ID", "0")),
    # Specific account to read/trade; blank = primary managed account.
    "ibkr_account_id": os.getenv("IBKR_ACCOUNT_ID", ""),
    # Market data: 1 real-time (needs subscription), 3 delayed (free).
    "ibkr_market_data_type": int(os.getenv("IBKR_MARKET_DATA_TYPE", "3")),
    # When True, a succeeded analysis run auto-creates a pending trade
    # proposal; when False (default) proposals are created manually.
    "ibkr_auto_propose": os.getenv("IBKR_AUTO_PROPOSE", "false").lower() == "true",
    # Redis list used as the connector command channel.
    "ibkr_cmd_queue": os.getenv("IBKR_CMD_QUEUE", "ibkr:commands"),

    # ------------------------------------------------------------------ #
    # Webull (Connect API — cloud REST, multi-tenant OAuth)               #
    # ------------------------------------------------------------------ #
    # Platform request-signing credentials (shared across users). The per-user
    # OAuth access token + account id are injected at request time by the broker
    # provider (see routers/broker.py), NOT read from env here.
    "webull_app_key": os.getenv("WEBULL_APP_KEY", ""),
    "webull_app_secret": os.getenv("WEBULL_APP_SECRET", ""),
    # Region: us / hk / jp / sg.
    "webull_region": os.getenv("WEBULL_REGION", "us"),
    # Optional explicit OAuth endpoint override (else derived from region+paper).
    "webull_endpoint": os.getenv("WEBULL_ENDPOINT", ""),
    # HTTP timeouts (seconds) for Webull API calls. Raise these when reaching the
    # US API across borders / through a proxy, where the SDK defaults time out.
    "webull_connect_timeout": float(os.getenv("WEBULL_CONNECT_TIMEOUT", "10") or 10),
    "webull_read_timeout": float(os.getenv("WEBULL_READ_TIMEOUT", "30") or 30),
    # Connect API OAuth app (issued by Webull on registration). Used by the
    # server-side OAuth flow; the per-user tokens it mints are stored encrypted.
    "webull_client_id": os.getenv("WEBULL_CLIENT_ID", ""),
    "webull_client_secret": os.getenv("WEBULL_CLIENT_SECRET", ""),
    "webull_redirect_uri": os.getenv("WEBULL_REDIRECT_URI", ""),
    "webull_scope": os.getenv("WEBULL_SCOPE", "trade account"),
    # Optional explicit OAuth base override (else derived from region+paper).
    "webull_oauth_base": os.getenv("WEBULL_OAUTH_BASE", ""),
    # Where to send the browser after a successful/failed OAuth callback.
    "webull_post_auth_redirect": os.getenv("WEBULL_POST_AUTH_REDIRECT", "/broker"),

    # ------------------------------------------------------------------ #
    # Watchlist                                                            #
    # ------------------------------------------------------------------ #
    # Tickers the scheduler will analyse every trading day.
    "watchlist": os.getenv("TRADINGBOT_WATCHLIST", "AAPL,MSFT,NVDA,GOOGL,AMZN").split(","),

    # ------------------------------------------------------------------ #
    # Position sizing (passed to SignalMapper)                             #
    # ------------------------------------------------------------------ #
    # Fraction of available cash allocated on a full BUY signal.
    "full_position_pct": float(os.getenv("FULL_POSITION_PCT", "0.05")),

    # Fraction of available cash allocated on an OVERWEIGHT signal.
    "partial_position_pct": float(os.getenv("PARTIAL_POSITION_PCT", "0.03")),

    # Fraction of existing position sold on an UNDERWEIGHT signal.
    "partial_exit_pct": float(os.getenv("PARTIAL_EXIT_PCT", "0.50")),

    # ------------------------------------------------------------------ #
    # Risk Gate hard limits                                                #
    # ------------------------------------------------------------------ #
    # Maximum fraction of total portfolio in a single position.
    "max_single_position_pct": float(os.getenv("MAX_SINGLE_POSITION_PCT", "0.10")),

    # Maximum fraction of portfolio invested at any time (rest stays cash).
    "max_total_exposure_pct": float(os.getenv("MAX_TOTAL_EXPOSURE_PCT", "0.80")),

    # Circuit breaker: halt new buys if daily P&L drops below this fraction.
    # e.g. -0.02 means halt if down more than 2 % today.
    "daily_loss_limit_pct": float(os.getenv("DAILY_LOSS_LIMIT_PCT", "-0.02")),

    # Minimum cash reserve to always keep available (absolute dollars).
    "min_cash_reserve": float(os.getenv("MIN_CASH_RESERVE", "1000.0")),

    # ------------------------------------------------------------------ #
    # Scheduler                                                            #
    # ------------------------------------------------------------------ #
    # Timezone for all schedule times.
    "timezone": "America/New_York",

    # Time to run pre-market analysis (HH:MM, 24-hour).
    "pre_market_time": os.getenv("PRE_MARKET_TIME", "08:00"),

    # Time to submit orders after market open.
    "order_submission_time": os.getenv("ORDER_SUBMISSION_TIME", "09:35"),

    # Time to run post-market reflection.
    "post_market_time": os.getenv("POST_MARKET_TIME", "16:30"),

    # ------------------------------------------------------------------ #
    # Paths                                                                #
    # ------------------------------------------------------------------ #
    # SQLite database used by PortfolioManager.
    "db_path": os.getenv(
        "TRADINGBOT_DB_PATH",
        os.path.join(os.path.expanduser("~"), ".tradingagents", "tradingbot.db"),
    ),

    # Directory where TradingAgentsGraph saves full per-run JSON logs.
    # Must match TRADINGAGENTS_RESULTS_DIR (or the DEFAULT_CONFIG default).
    # The dashboard reads from here to show full agent reasoning per trade.
    "results_dir": os.getenv(
        "TRADINGAGENTS_RESULTS_DIR",
        os.path.join(os.path.expanduser("~"), ".tradingagents", "logs"),
    ),
}
