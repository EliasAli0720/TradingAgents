import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getBrokerChannel } from '@/api/brokerChannel';

// Single source of truth for broker connectivity. Polls the active channel's
// status; `tradingEnabled` is what the gate and trade actions check.
export function useBrokerConnection() {
  const channel = useMemo(() => getBrokerChannel(), []);
  const q = useQuery({
    queryKey: ['broker', 'status'],
    queryFn: () => channel.status(),
    refetchInterval: 5000,
    retry: 1,
  });
  const s = q.data ?? null;
  return {
    channel,
    status: s,
    isLoading: q.isLoading,
    isError: q.isError,
    connected: Boolean(s?.connected),
    tradingEnabled: Boolean(s?.connected && s?.brokerage_session),
    refetch: q.refetch,
  };
}
