import { useEffect, useRef } from 'react';
import { brokerApi } from '@/api/broker';
import { getBrokerChannel } from '@/api/brokerChannel';
import { useBrokerConnection } from './useBrokerConnection';

// While a broker account is connected, periodically push the live account
// equity to the server so the per-(user, account) equity curve / Sharpe /
// drawdown have a time series. One row per (user, account, day), updated to the
// latest value. Best-effort: failures are swallowed.
export function useSnapshotPush() {
  const { status, tradingEnabled } = useBrokerConnection();
  const accountId = status?.account_id ?? '';
  const broker = status?.broker ?? 'ibkr';
  const busy = useRef(false);

  useEffect(() => {
    if (!tradingEnabled || !accountId) return;
    const channel = getBrokerChannel();
    let cancelled = false;

    const push = async () => {
      if (busy.current) return;
      busy.current = true;
      try {
        const [acct, positions] = await Promise.all([channel.account(), channel.positions()]);
        if (cancelled) return;
        const invested = positions.reduce((s, p) => s + p.market_value, 0);
        await brokerApi.pushSnapshot({
          account_id: accountId,
          broker,
          cash: acct.cash,
          invested_value: invested,
          total_value: acct.equity || acct.portfolio_value,
          open_positions: positions.length,
        });
      } catch {
        /* best effort */
      } finally {
        busy.current = false;
      }
    };

    push();
    const id = setInterval(push, 5 * 60 * 1000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [tradingEnabled, accountId, broker]);
}
