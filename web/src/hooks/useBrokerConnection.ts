import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getBrokerChannel } from '@/api/brokerChannel';

// Single source of truth for broker connectivity. Polls the active channel's
// status; `tradingEnabled` is what the gate and trade actions check.
export function useBrokerConnection() {
  const channel = useMemo(() => getBrokerChannel(), []);
  const isServer = channel.kind === 'server';
  // The local (IBKR) channel needs frequent liveness polling — the local TWS /
  // IB Gateway session can drop at any time. The server (Webull) channel is a
  // stateless cloud REST broker whose link state only changes on connect /
  // disconnect / token expiry (those invalidate this query directly), so poll
  // it far less often instead of hammering /broker/status every 5s.
  const q = useQuery({
    queryKey: ['broker', 'status'],
    queryFn: () => channel.status(),
    refetchInterval: isServer ? 30000 : 5000,
    retry: 1,
  });
  const s = q.data ?? null;
  return {
    channel,
    status: s,
    isLoading: q.isLoading,
    isError: q.isError,
    connected: Boolean(s?.connected),
    // brokerage_session is an IBKR (local TWS) concept; for the server (Webull)
    // channel "connected" alone means trading is enabled.
    tradingEnabled: isServer ? Boolean(s?.connected) : Boolean(s?.connected && s?.brokerage_session),
    refetch: q.refetch,
  };
}
