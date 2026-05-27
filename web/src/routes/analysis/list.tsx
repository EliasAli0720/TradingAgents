import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { adminApi } from '@/api/admin';
import { useAuth } from '@/hooks/useAuth';
import { Subheader, Caption, Info } from '@/components/ui/Page';
import { t } from '@/i18n';

export default function AnalysisListPage() {
  const { isAdmin } = useAuth();
  const q = useQuery({
    queryKey: ['runs', 'list'],
    queryFn: () => adminApi.runs(),
    enabled: isAdmin,
  });

  return (
    <div>
      <Subheader>{t('sig.subheader')}</Subheader>
      <Caption>{t('sig.caption')}</Caption>

      <div className="flex justify-end mb-3">
        <Link to="/analysis/new" className="btn-primary">{t('nav.analysis_new')}</Link>
      </div>

      {!isAdmin ? (
        <Info>
          当前账号是 viewer / operator。后端尚未提供 <code className="font-mono">GET /runs</code>（当前用户视角）。
          可直接通过「新建分析」创建任务并打开详情页查看进度。
        </Info>
      ) : q.isLoading ? (
        <div className="text-muted">{t('common.loading')}</div>
      ) : q.error ? (
        <div className="text-danger">加载失败</div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="df">
            <thead>
              <tr>
                <th>股票代码</th>
                <th>分析日期</th>
                <th>状态</th>
                <th>创建时间</th>
                <th>完成时间</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {q.data?.map((r) => (
                <tr key={r.run_id}>
                  <td className="font-mono">{r.ticker}</td>
                  <td>{r.trade_date}</td>
                  <td><StatusBadge status={r.status} /></td>
                  <td className="text-muted">{fmtTime(r.created_at)}</td>
                  <td className="text-muted">{r.finished_at ? fmtTime(r.finished_at) : '—'}</td>
                  <td><Link to={`/analysis/${r.run_id}`} className="text-[#ff4b4b]">详情</Link></td>
                </tr>
              ))}
              {q.data?.length === 0 && (
                <tr><td colSpan={6} className="py-4 text-muted text-center">{t('common.empty')}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function fmtTime(iso: string): string {
  try { return new Date(iso).toLocaleString('zh-CN', { hour12: false }); } catch { return iso; }
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    queued: 'bg-neutralBg text-muted',
    running: 'bg-infoBg text-info',
    succeeded: 'bg-successBg text-success',
    failed: 'bg-dangerBg text-danger',
    cancelled: 'bg-warnBg text-warn',
  };
  return <span className={`badge ${map[status] ?? 'bg-white/10'}`}>{status}</span>;
}
