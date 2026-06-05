import type { TradeApproval } from './broker';

export type ProposalReportRow = {
  labelKey: string;
  value: string;
};

type ProposalReport = {
  summary?: string;
  signal?: {
    raw?: string;
    normalized?: string;
    action?: string;
    reason?: string;
  };
  sizing?: {
    basis?: string;
    basis_amount?: number;
    allocation_fraction?: number;
    target_value?: number;
    estimated_price?: number;
    computed_quantity?: number;
    final_quantity?: number;
    estimated_value?: number;
  };
  risk?: {
    approved?: boolean | null;
    reason?: string;
    adjusted_qty?: number | null;
  };
  agent_reasoning?: string;
};

function report(a: TradeApproval): ProposalReport | null {
  return (a.proposal_report as ProposalReport | null) ?? null;
}

function fmt(n: unknown, digits = 2): string {
  return typeof n === 'number' && Number.isFinite(n) ? n.toFixed(digits) : '-';
}

function pct(n: unknown): string {
  return typeof n === 'number' && Number.isFinite(n) ? `${(n * 100).toFixed(2)}%` : '-';
}

export function proposalReportSummary(a: TradeApproval): string {
  const r = report(a);
  if (r?.summary) return r.summary;
  return `${a.side.toUpperCase()} ${a.ticker} ${a.quantity} @ ${fmt(a.estimated_price)}`;
}

export function proposalReportRows(a: TradeApproval): ProposalReportRow[] {
  const r = report(a);
  if (!r) {
    return a.agent_reasoning
      ? [{ labelKey: 'broker.proposal_report.reasoning', value: a.agent_reasoning }]
      : [];
  }

  const rows: ProposalReportRow[] = [];
  const signal = r.signal;
  if (signal?.normalized) {
    rows.push({
      labelKey: 'broker.proposal_report.signal',
      value: `${signal.normalized}${signal.raw ? ` (raw: ${signal.raw})` : ''}`,
    });
  }

  const sizing = r.sizing;
  if (sizing) {
    rows.push({
      labelKey: 'broker.proposal_report.sizing',
      value: `${sizing.basis ?? '-'} ${fmt(sizing.basis_amount)} x ${pct(sizing.allocation_fraction)} / ${fmt(
        sizing.estimated_price,
      )} = ${fmt(sizing.computed_quantity)} -> ${sizing.final_quantity ?? '-'} shares`,
    });
    rows.push({
      labelKey: 'broker.proposal_report.estimated_value',
      value: fmt(sizing.estimated_value),
    });
  }

  const risk = r.risk;
  if (risk) {
    const status = risk.approved === true ? 'approved' : risk.approved === false ? 'blocked' : 'checked';
    const adjusted = risk.adjusted_qty != null ? `; adjusted qty ${risk.adjusted_qty}` : '';
    rows.push({
      labelKey: 'broker.proposal_report.risk',
      value: `${status} - ${risk.reason ?? '-'}${adjusted}`,
    });
  }

  const reasoning = r.agent_reasoning ?? a.agent_reasoning;
  if (reasoning) {
    rows.push({ labelKey: 'broker.proposal_report.reasoning', value: reasoning });
  }
  return rows;
}
