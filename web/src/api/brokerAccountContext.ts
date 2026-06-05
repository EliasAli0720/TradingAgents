import type { BrokerStatus } from './broker';

export type BrokerAccountSource = 'server' | 'local';

export type BrokerAccountOption = {
  key: string;
  source: BrokerAccountSource;
  broker: string;
  account_id: string;
  paper: boolean;
  label: string;
};

type Input = {
  serverStatus?: Pick<BrokerStatus, 'broker' | 'connected' | 'brokerage_session' | 'account_id' | 'accounts' | 'paper'> | null;
  localStatus?: Pick<BrokerStatus, 'broker' | 'connected' | 'brokerage_session' | 'account_id' | 'accounts' | 'paper'> | null;
  includeLocal: boolean;
};

type UsableStatus = NonNullable<Input['serverStatus']>;

function accountIds(status?: Input['serverStatus']): string[] {
  const candidates = [status?.account_id, ...(status?.accounts ?? [])];
  const out: string[] = [];
  for (const candidate of candidates) {
    const accountId = (candidate ?? '').trim();
    if (accountId && !out.includes(accountId)) out.push(accountId);
  }
  return out;
}

function usable(status?: Input['serverStatus']): status is UsableStatus {
  if (!status?.connected || accountIds(status).length === 0) return false;
  if ((status.broker ?? '').toLowerCase() === 'webull') return true;
  return Boolean(status.brokerage_session);
}

function pushOptions(out: BrokerAccountOption[], source: BrokerAccountSource, status: UsableStatus): void {
  const broker = (status.broker || 'ibkr').toLowerCase();
  const local = source === 'local';
  for (const account_id of accountIds(status)) {
    out.push({
      key: `${source}:${broker}:${account_id}`,
      source,
      broker,
      account_id,
      paper: status.paper ?? true,
      label: `${broker.toUpperCase()}${local ? ' Local' : ''} · ${account_id}`,
    });
  }
}

export function brokerAccountOptions(input: Input): BrokerAccountOption[] {
  const out: BrokerAccountOption[] = [];
  if (usable(input.serverStatus)) {
    pushOptions(out, 'server', input.serverStatus);
  }
  if (input.includeLocal && usable(input.localStatus)) {
    pushOptions(out, 'local', input.localStatus);
  }
  return out;
}

export function defaultBrokerAccountKey(options: BrokerAccountOption[]): string {
  return options[0]?.key ?? '';
}

export function resolveBrokerAccountKey(options: BrokerAccountOption[], preferredKey?: string | null): string {
  if (preferredKey && options.some((option) => option.key === preferredKey)) {
    return preferredKey;
  }
  return defaultBrokerAccountKey(options);
}
