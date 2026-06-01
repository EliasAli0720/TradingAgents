import type { BrokerStatus } from './broker';
import { isUsableBrokerStatus, shouldUseServerProposal } from './brokerReadiness';

export type ManualTradeRoute = 'server' | 'local' | null;

export function manualTradeRoute(input: {
  desktop: boolean;
  serverStatus?: BrokerStatus | null;
  serverStatusLoading?: boolean;
  localStatus?: BrokerStatus | null;
  localCanExecute?: boolean;
}): ManualTradeRoute {
  if (shouldUseServerProposal(input.serverStatus)) {
    return 'server';
  }
  if (
    input.desktop &&
    !input.serverStatusLoading &&
    input.localCanExecute &&
    isUsableBrokerStatus(input.localStatus)
  ) {
    return 'local';
  }
  return null;
}
