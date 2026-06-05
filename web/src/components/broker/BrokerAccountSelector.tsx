import type { BrokerAccountOption } from '@/api/brokerAccountContext';
import { t } from '@/i18n';

export default function BrokerAccountSelector({
  options,
  selectedKey,
  onChange,
}: {
  options: BrokerAccountOption[];
  selectedKey: string;
  onChange: (key: string) => void;
}) {
  if (options.length <= 1) return null;
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-muted">{t('broker.account.select')}</span>
      <select className="input max-w-xs" value={selectedKey} onChange={(e) => onChange(e.target.value)}>
        {options.map((option) => (
          <option key={option.key} value={option.key}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
