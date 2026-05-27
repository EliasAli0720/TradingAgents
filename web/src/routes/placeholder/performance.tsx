import { Subheader, Info } from '@/components/ui/Page';
import Metric, { KpiRow } from '@/components/ui/Metric';
import { t } from '@/i18n';

export default function PerformancePage() {
  return (
    <div>
      <Subheader>{t('nav.performance')}</Subheader>
      <KpiRow>
        <Metric label={t('performance.total_return')} value="—" />
        <Metric label={t('performance.sharpe')} value="—" />
        <Metric label={t('performance.max_drawdown')} value="—" />
        <Metric label={t('performance.win_rate')} value="—" />
      </KpiRow>
      <div className="mt-4" />
      <KpiRow>
        <Metric label={t('performance.total_trades')} value="—" />
        <Metric label={t('performance.avg_win')} value="—" />
        <Metric label={t('performance.avg_loss')} value="—" />
        <Metric label={t('performance.profit_factor')} value="—" />
      </KpiRow>
      <div className="mt-6">
        <Info>{t('performance.phase3')}</Info>
      </div>
      <Subheader>{t('performance.equity')}</Subheader>
      <div className="card text-muted text-sm">{t('common.empty')}</div>
      <Subheader>{t('performance.drawdown')}</Subheader>
      <div className="card text-muted text-sm">{t('common.empty')}</div>
      <Subheader>{t('performance.daily_pnl')}</Subheader>
      <div className="card text-muted text-sm">{t('common.empty')}</div>
    </div>
  );
}
