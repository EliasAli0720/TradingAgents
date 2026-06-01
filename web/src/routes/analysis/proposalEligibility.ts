const ACTIONABLE_SIGNALS = new Set(['BUY', 'OVERWEIGHT', 'UNDERWEIGHT', 'SELL']);

export type ProposalEligibilityState = 'hidden' | 'waiting' | 'actionable' | 'no_action' | 'connect_account';

export type ProposalEligibilityInput = {
  canOperate: boolean;
  runStatus: string;
  decision?: string | null;
  brokerStatusLoading?: boolean;
  hasUsableBrokerAccount?: boolean;
};

export type ProposalEligibility = {
  state: ProposalEligibilityState;
  signal: string;
};

export function normalizeProposalSignal(decision?: string | null): string {
  return (decision ?? '').trim().toUpperCase();
}

export function proposalEligibility(input: ProposalEligibilityInput): ProposalEligibility {
  if (!input.canOperate || input.runStatus !== 'succeeded') {
    return { state: 'hidden', signal: '' };
  }

  const signal = normalizeProposalSignal(input.decision);
  if (!signal) {
    return { state: 'waiting', signal: '' };
  }
  if (ACTIONABLE_SIGNALS.has(signal)) {
    if (input.brokerStatusLoading) {
      return { state: 'waiting', signal };
    }
    if (input.hasUsableBrokerAccount === false) {
      return { state: 'connect_account', signal };
    }
    return { state: 'actionable', signal };
  }
  return { state: 'no_action', signal };
}

export function proposalButtonLabelKey(isPending: boolean): string {
  return isPending ? 'broker.proposal.generating' : 'broker.proposal.generate';
}
