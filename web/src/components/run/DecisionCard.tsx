// Top-of-page decision card. Extracts SIGNAL / Action / Entry / Stop / Target / Horizon
// from the reports' free-text markdown.

import { t, getLang } from '@/i18n';

const SIGNAL_COLORS: Record<string, { fg: string; bg: string }> = {
  BUY:         { fg: '#4CAF50', bg: '#1b2a1d' },
  OVERWEIGHT:  { fg: '#4CAF50', bg: '#1b2a1d' },
  HOLD:        { fg: '#37474F', bg: '#1c2126' },
  UNDERWEIGHT: { fg: '#FFB300', bg: '#2a2417' },
  SELL:        { fg: '#F44336', bg: '#2a1818' },
};

function pick(re: RegExp, ...sources: (string | undefined)[]): string | null {
  for (const s of sources) {
    if (!s) continue;
    const m = s.match(re);
    if (m) return m[1].trim();
  }
  return null;
}

export type DecisionInputs = {
  decision?: string | null;          // top-level
  final_trade_decision?: string;
  trader_investment_plan?: string;
};

export default function DecisionCard({ inputs }: { inputs: DecisionInputs }) {
  const final = inputs.final_trade_decision ?? '';
  const trader = inputs.trader_investment_plan ?? '';

  const rating = (
    pick(/\*\*Rating\*\*[:：]\s*([A-Za-z]+)/, final) ||
    pick(/\*\*Action\*\*[:：]\s*([A-Za-z]+)/, trader) ||
    inputs.decision ||
    ''
  ).toUpperCase();

  const color = SIGNAL_COLORS[rating];

  const action = pick(/\*\*Action\*\*[:：]\s*([A-Za-z]+)/, trader);
  const entry  = pick(/\*\*(?:Entry Price|Entry)\*\*[:：]\s*([^\n]+)/, trader, final);
  const stop   = pick(/\*\*Stop Loss\*\*[:：]\s*([^\n]+)/, trader, final);
  const target = pick(/\*\*Price Target\*\*[:：]\s*([^\n]+)/, final, trader);
  const size   = pick(/\*\*Position Sizing\*\*[:：]\s*([^\n]+)/, trader, final);
  const horiz  = pick(/\*\*Time Horizon\*\*[:：]\s*([^\n]+)/, final, trader);
  const summary = pick(/\*\*Executive Summary\*\*[:：]\s*([\s\S]+?)(?:\n\n|\*\*Investment Thesis\*\*)/, final);

  if (!rating && !action) return null;

  return (
    <div
      className="rounded-lg border-2 p-5 mb-5"
      style={{
        background: color?.bg ?? '#1c2126',
        borderColor: color?.fg ?? '#37474F',
      }}
    >
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <div>
          <div className="text-xs uppercase tracking-widest text-muted">{t('decision.final_signal')}</div>
          <div className="text-3xl font-bold" style={{ color: color?.fg ?? '#fafafa' }}>
            {rating || '—'}
          </div>
        </div>
        {action && (
          <Field label={t('decision.action')} value={action} color={color?.fg} />
        )}
        {entry && <Field label={t('decision.entry')} value={entry} />}
        {stop  && <Field label={t('decision.stop')} value={stop} />}
        {target && <Field label={t('decision.target')} value={target} />}
        {size  && <Field label={t('decision.size')} value={size} />}
        {horiz && <Field label={t('decision.horizon')} value={horiz} />}
      </div>

      {summary && getLang() === 'en' && (
        <div className="mt-4 pt-4 border-t border-border/40">
          <div className="text-xs uppercase tracking-widest text-muted mb-1">{t('decision.summary')}</div>
          <div className="text-sm leading-6 text-text/90">{summary}</div>
        </div>
      )}
    </div>
  );
}

function Field({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-widest text-muted">{label}</div>
      <div className="text-base font-semibold" style={{ color: color ?? '#fafafa' }}>{value}</div>
    </div>
  );
}
