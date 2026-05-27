import { Subheader, Info } from '@/components/ui/Page';
import Metric, { KpiRow } from '@/components/ui/Metric';
import { t } from '@/i18n';

export default function PortfolioPage() {
  return (
    <div>
      <Subheader>{t('portfolio.current')}</Subheader>
      <KpiRow>
        <Metric label={t('portfolio.total_value')} value="—" />
        <Metric label={t('portfolio.cash')} value="—" />
        <Metric label={t('portfolio.invested')} value="—" />
        <Metric label={t('portfolio.unrealized_pnl')} value="—" />
      </KpiRow>
      <div className="mt-6">
        <Info>{t('portfolio.phase3')}</Info>
      </div>
      <div className="mt-6" />
      <Subheader>{t('portfolio.allocation')}</Subheader>
      <div className="card text-muted text-sm">{t('common.empty')}</div>
    </div>
  );
}
