"""Server-side trade services: turn analysis decisions into reviewed, executed
broker orders without the blocking CLI approval prompt.

- TradeProposalBuilder: decision -> sized, risk-checked, persisted approval.
- TradeExecutionService: approved -> re-checked, previewed, placed order.
- BrokerConnectionService: build the server (Redis-proxied) broker + status.
"""

from .broker_connection import BrokerConnectionService
from .trade_execution import (
    ExecutionResult,
    TradeExecutionService,
    build_execution_service,
)
from .trade_proposal import (
    ProposalOutcome,
    TradeProposalBuilder,
    build_proposal_builder,
)

__all__ = [
    "BrokerConnectionService",
    "ExecutionResult",
    "TradeExecutionService",
    "build_execution_service",
    "ProposalOutcome",
    "TradeProposalBuilder",
    "build_proposal_builder",
]
