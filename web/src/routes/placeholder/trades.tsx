import { Subheader, Info } from '@/components/ui/Page';
import Metric, { KpiRow } from '@/components/ui/Metric';

export default function TradesPage() {
  return (
    <div>
      <Subheader>交易记录</Subheader>
      <KpiRow>
        <Metric label="总交易笔数" value="—" />
        <Metric label="买入" value="—" />
        <Metric label="卖出" value="—" />
        <Metric label="已实现盈亏" value="—" />
      </KpiRow>
      <div className="mt-6">
        <Info>Phase 3 待办：<code className="font-mono">{'GET /trades · /trades/{id} · /trades/closed'}</code>。</Info>
      </div>
      <Subheader>每笔交易明细</Subheader>
      <div className="card text-muted text-sm">暂无数据</div>
      <Subheader>已平仓交易</Subheader>
      <div className="card text-muted text-sm">暂无数据</div>
    </div>
  );
}
