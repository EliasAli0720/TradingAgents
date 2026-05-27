// Streamlit-like st.metric: label, big value, optional delta with up/down arrow.
import clsx from 'clsx';

export type MetricProps = {
  label: string;
  value: React.ReactNode;
  delta?: string | null;
  deltaPositive?: boolean | null; // null = neutral
  inverse?: boolean;              // green=down semantics (e.g., drawdown)
};

export default function Metric({ label, value, delta, deltaPositive, inverse }: MetricProps) {
  let cls = 'metric-delta';
  let arrow = '';
  if (delta != null) {
    const positive = deltaPositive ?? false;
    const good = inverse ? !positive : positive;
    cls = clsx('metric-delta', good ? 'metric-delta-up' : 'metric-delta-down');
    arrow = positive ? '▲ ' : '▼ ';
  }
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {delta != null && <div className={cls}>{arrow}{delta}</div>}
    </div>
  );
}

export function KpiRow({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">{children}</div>;
}
