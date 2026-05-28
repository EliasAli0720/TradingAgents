import pytest

from tradingagents.worker.cancellation import AnalysisCancelled, CancellationToken


def test_cancellation_token_raises_when_cancelled():
    token = CancellationToken(lambda: True)

    with pytest.raises(AnalysisCancelled):
        token.raise_if_cancelled()


def test_cancellation_token_allows_when_not_cancelled():
    token = CancellationToken(lambda: False)

    token.raise_if_cancelled()
