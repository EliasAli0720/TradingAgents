import { Subheader, Info } from '@/components/ui/Page';
import Metric, { KpiRow } from '@/components/ui/Metric';

export default function RiskPage() {
  return (
    <div>
      <Subheader>风险监控</Subheader>
      <KpiRow>
        <Metric label="投资比例" value="—" />
        <Metric label="可用现金" value="—" />
        <Metric label="已投资金额" value="—" />
        <Metric label="敞口" value="—" />
      </KpiRow>
      <div className="mt-6">
        <Info>Phase 3 待办：<code className="font-mono">GET /risk/exposure · /risk/config</code>。</Info>
      </div>
      <Subheader>熔断器</Subheader>
      <div className="card text-muted text-sm">暂无数据</div>
      <Subheader>总仓位敞口</Subheader>
      <div className="card text-muted text-sm">暂无数据</div>
      <Subheader>单票集中度</Subheader>
      <div className="card text-muted text-sm">暂无数据</div>
    </div>
  );
}
