const ACTIONABLE_SIGNALS = new Set(['BUY', 'OVERWEIGHT', 'UNDERWEIGHT', 'SELL']);
const ALL_SIGNALS = new Set([...ACTIONABLE_SIGNALS, 'HOLD']);
const RATING_LABEL_RE = /\brating\**\s*[:\-]\s*\**(buy|overweight|hold|underweight|sell)\b/i;

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
  const raw = (decision ?? '').trim();
  const exact = raw.replace(/^[*:.,\s]+|[*:.,\s]+$/g, '').toUpperCase();
  if (ALL_SIGNALS.has(exact)) return exact;

  const match = raw.match(RATING_LABEL_RE);
  return match ? match[1].toUpperCase() : exact;
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
