// Channel-aware proposal + execution. The approval audit always lives on the
// server; only *placement* differs by channel:
//   server channel — the server places the order (existing /broker flow)
//   local channel  — the local sidecar places it against the local TWS, and we
//                    report the result back to the server (decision B).
import { brokerApi, type TradeApproval } from './broker';
import { getBrokerChannel } from './brokerChannel';
import { brokerNotConnectedError, isUsableBrokerStatus, shouldUseServerProposal } from './brokerReadiness';

export async function createProposal(runId: string, ticker: string): Promise<TradeApproval> {
  const channel = getBrokerChannel();
  const serverStatus = await brokerApi.status();

  // Webull is a per-user cloud broker exposed only through the server API.
  // Desktop may still have a local IBKR sidecar, but an active Webull account
  // must not fall through to local quote/snapshot collection.
  if (shouldUseServerProposal(serverStatus)) {
    return brokerApi.createProposal(runId);
  }

  if (channel.kind === 'server' || !channel.quote) {
    if (!isUsableBrokerStatus(serverStatus)) {
      throw brokerNotConnectedError();
    }
    return brokerApi.createProposal(runId);
  }

  const localStatus = await channel.status();
  if (!isUsableBrokerStatus(localStatus)) {
    throw brokerNotConnectedError();
  }

  // Local: gather the live inputs the server needs to size + risk-check.
  const [account, positions, quote] = await Promise.all([
    channel.account(),
    channel.positions(),
    channel.quote(ticker),
  ]);
  return brokerApi.createLocalProposal({ run_id: runId, account, positions, price: quote.price });
}

export async function approveProposal(a: TradeApproval): Promise<void> {
  const channel = getBrokerChannel();
  const serverStatus = await brokerApi.status();
  if (shouldUseServerProposal(serverStatus)) {
    await brokerApi.approve(a.approval_id);
    return;
  }
  if (channel.kind === 'server' || !channel.execute) {
    if (!isUsableBrokerStatus(serverStatus)) {
      throw brokerNotConnectedError();
    }
    await brokerApi.approve(a.approval_id);
    return;
  }
  // Local: place against the local TWS, then record the placement on the server
  // tagged with the connected account so analytics segment per (user, account).
  const status = await channel.status();
  if (!isUsableBrokerStatus(status)) {
    throw brokerNotConnectedError();
  }
  const placed = await channel.execute({
    ticker: a.ticker,
    qty: a.quantity,
    side: a.side as 'buy' | 'sell',
    order_type: (a.order_type as 'market' | 'limit') ?? 'market',
    limit_price: a.limit_price ?? undefined,
    time_in_force: a.time_in_force ?? 'day',
  });
  await brokerApi.recordExecuted(a.approval_id, {
    broker_order_id: placed.broker_order_id,
    status: placed.status,
    filled_qty: placed.filled_qty,
    filled_avg_price: placed.filled_avg_price,
    limit_price: placed.limit_price,
    account_id: status.account_id ?? undefined,
  });
}
