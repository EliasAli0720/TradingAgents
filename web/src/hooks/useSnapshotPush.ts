import { useEffect, useRef } from 'react';
import { brokerApi } from '@/api/broker';
import { useBrokerAccountContext } from './useBrokerAccountContext';

// While a broker account is connected, periodically push the live account
// equity to the server so the per-(user, account) equity curve / Sharpe /
// drawdown have a time series. One row per (user, account, day), updated to the
// latest value. Best-effort: failures are swallowed.
export function useSnapshotPush() {
  const { account, positions, selected } = useBrokerAccountContext();
  const busy = useRef(false);
  const selectedAccountId = selected?.account_id;
  const selectedBroker = selected?.broker;
  const selectedKey = selected?.key;

  useEffect(() => {
    if (!selectedAccountId || !selectedBroker) return;
    let cancelled = false;

    const push = async () => {
      if (busy.current) return;
      busy.current = true;
      try {
        const [acct, currentPositions] = await Promise.all([account(), positions()]);
        if (cancelled) return;
        const invested = currentPositions.reduce((s, p) => s + p.market_value, 0);
        await brokerApi.pushSnapshot({
          account_id: selectedAccountId,
          broker: selectedBroker,
          cash: acct.cash,
          invested_value: invested,
          total_value: acct.equity || acct.portfolio_value,
          open_positions: currentPositions.length,
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
  }, [account, positions, selectedAccountId, selectedBroker, selectedKey]);
}
