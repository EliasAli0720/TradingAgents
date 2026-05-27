import { Subheader, Info } from '@/components/ui/Page';
import Metric, { KpiRow } from '@/components/ui/Metric';

export default function PerformancePage() {
  return (
    <div>
      <Subheader>业绩</Subheader>
      <KpiRow>
        <Metric label="总收益" value="—" />
        <Metric label="夏普比率" value="—" />
        <Metric label="最大回撤" value="—" />
        <Metric label="胜率" value="—" />
      </KpiRow>
      <div className="mt-4" />
      <KpiRow>
        <Metric label="总交易笔数" value="—" />
        <Metric label="平均盈利" value="—" />
        <Metric label="平均亏损" value="—" />
        <Metric label="盈亏比" value="—" />
      </KpiRow>
      <div className="mt-6">
        <Info>Phase 3 待办：<code className="font-mono">GET /performance/equity · /drawdown · /daily-pnl</code>。</Info>
      </div>
      <Subheader>净值曲线</Subheader>
      <div className="card text-muted text-sm">暂无数据</div>
      <Subheader>回撤</Subheader>
      <div className="card text-muted text-sm">暂无数据</div>
      <Subheader>每日盈亏</Subheader>
      <div className="card text-muted text-sm">暂无数据</div>
    </div>
  );
}
