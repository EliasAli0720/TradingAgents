import { Subheader, Info } from '@/components/ui/Page';
import Metric, { KpiRow } from '@/components/ui/Metric';
import { t } from '@/i18n';

export default function RiskPage() {
  return (
    <div>
      <Subheader>{t('nav.risk')}</Subheader>
      <KpiRow>
        <Metric label={t('risk.investment_ratio')} value="—" />
        <Metric label={t('risk.cash_available')} value="—" />
        <Metric label={t('risk.invested_amount')} value="—" />
        <Metric label={t('risk.exposure')} value="—" />
      </KpiRow>
      <div className="mt-6">
        <Info>{t('risk.phase3')}</Info>
      </div>
      <Subheader>{t('risk.circuit_breaker')}</Subheader>
      <div className="card text-muted text-sm">{t('common.empty')}</div>
      <Subheader>{t('risk.total_exposure')}</Subheader>
      <div className="card text-muted text-sm">{t('common.empty')}</div>
      <Subheader>{t('risk.concentration')}</Subheader>
      <div className="card text-muted text-sm">{t('common.empty')}</div>
    </div>
  );
}
