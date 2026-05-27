import { Subheader, Info } from '@/components/ui/Page';
import Metric, { KpiRow } from '@/components/ui/Metric';
import { t } from '@/i18n';

export default function PortfolioPage() {
  return (
    <div>
      <Subheader>当前持仓</Subheader>
      <KpiRow>
        <Metric label="投资组合总值" value="—" />
        <Metric label="现金" value="—" />
        <Metric label="已投资" value="—" />
        <Metric label="未实现盈亏" value="—" />
      </KpiRow>
      <div className="mt-6">
        <Info>
          Phase 3 待办：后端需新增 <code className="font-mono">GET /portfolio/positions</code> 与{' '}
          <code className="font-mono">GET /portfolio/allocation</code>。
          目前布局已按 Streamlit 原版 1:1 复刻（KPI · 4 列 + 持仓表 + 分布饼图）。
        </Info>
      </div>
      <div className="mt-6" />
      <Subheader>持仓分布</Subheader>
      <div className="card text-muted text-sm">{t('common.empty')}</div>
    </div>
  );
}
