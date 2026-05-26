from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from tradingagents.api.schemas import CreateRunRequest


def test_create_run_request_normalizes_ticker():
    req = CreateRunRequest(
        ticker="nvda",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market", "news"],
    )
    assert req.ticker == "NVDA"


def test_create_run_request_rejects_invalid_ticker():
    with pytest.raises(ValidationError):
        CreateRunRequest(
            ticker="../NVDA",
            trade_date=date(2026, 1, 15),
            asset_type="stock",
            analysts=["market"],
        )


def test_create_run_request_rejects_future_date():
    with pytest.raises(ValidationError):
        CreateRunRequest(
            ticker="NVDA",
            trade_date=date.today() + timedelta(days=1),
            asset_type="stock",
            analysts=["market"],
        )


def test_create_run_request_rejects_crypto_fundamentals():
    with pytest.raises(ValidationError):
        CreateRunRequest(
            ticker="BTC-USD",
            trade_date=date(2026, 1, 15),
            asset_type="crypto",
            analysts=["market", "fundamentals"],
        )
