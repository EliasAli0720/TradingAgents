import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { brokerApi } from '@/api/broker';
import { shouldUseServerProposal } from '@/api/brokerReadiness';
import { useBrokerConnection } from '@/hooks/useBrokerConnection';
import { t } from '@/i18n';
import ConnectPanel from './ConnectPanel';

// Gates trading routes behind a live broker connection. Only the desktop local
// channel enforces "connect first" — server-managed channels (browser build /
// future cloud brokers) pass through and let the pages show their own status,
// preserving existing behavior.
export default function BrokerGate({ children }: { children: ReactNode }) {
  const conn = useBrokerConnection();
  const serverStatus = useQuery({
    queryKey: ['broker', 'status', 'server'],
    queryFn: () => brokerApi.status(),
    enabled: conn.channel.kind === 'local',
    refetchInterval: 30000,
    retry: 1,
  });

  if (conn.channel.kind === 'server') return <>{children}</>;
  if (shouldUseServerProposal(serverStatus.data)) return <>{children}</>;
  if (conn.isLoading) return <div className="text-muted">{t('common.loading')}</div>;
  if (conn.tradingEnabled) return <>{children}</>;
  return <ConnectPanel />;
}
