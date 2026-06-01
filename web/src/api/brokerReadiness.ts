export type BrokerStatusLike = {
  broker?: string | null;
  connected?: boolean | null;
  brokerage_session?: boolean | null;
  account_id?: string | null;
};

export function isUsableBrokerStatus(status?: BrokerStatusLike | null): boolean {
  if (!status?.connected || !status.account_id) {
    return false;
  }
  const broker = (status.broker ?? '').toLowerCase();
  if (broker === 'webull') {
    return true;
  }
  return Boolean(status.brokerage_session);
}

export function shouldUseServerProposal(status?: BrokerStatusLike | null): boolean {
  return (status?.broker ?? '').toLowerCase() === 'webull' && isUsableBrokerStatus(status);
}

export function brokerNotConnectedError(): { status: number; detail: string } {
  return { status: 0, detail: 'broker_not_connected' };
}
