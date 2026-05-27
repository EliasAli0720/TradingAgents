import { Subheader, Info } from '@/components/ui/Page';
import Metric, { KpiRow } from '@/components/ui/Metric';
import { t } from '@/i18n';

export default function TradesPage() {
  return (
    <div>
      <Subheader>{t('nav.trades')}</Subheader>
      <KpiRow>
        <Metric label={t('trades.total')} value="—" />
        <Metric label={t('trades.buy')} value="—" />
        <Metric label={t('trades.sell')} value="—" />
        <Metric label={t('trades.realized_pnl')} value="—" />
      </KpiRow>
      <div className="mt-6">
        <Info>{t('trades.phase3')}</Info>
      </div>
      <Subheader>{t('trades.details')}</Subheader>
      <div className="card text-muted text-sm">{t('common.empty')}</div>
      <Subheader>{t('trades.closed')}</Subheader>
      <div className="card text-muted text-sm">{t('common.empty')}</div>
    </div>
  );
}
