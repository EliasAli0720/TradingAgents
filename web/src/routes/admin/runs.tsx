import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { adminApi } from '@/api/admin';
import type { RunStatus } from '@/api/runs';
import { Subheader, Caption } from '@/components/ui/Page';
import { StatusBadge } from '../analysis/list';
import { t } from '@/i18n';

const STATUSES: (RunStatus | '')[] = ['', 'queued', 'running', 'succeeded', 'failed', 'cancelled'];

export default function AdminRunsPage() {
  const [userId, setUserId] = useState('');
  const [status, setStatus] = useState<RunStatus | ''>('');

  const q = useQuery({
    queryKey: ['admin', 'runs', userId, status],
    queryFn: () => adminApi.runs({
      user_id: userId || undefined,
      status_filter: (status || undefined) as RunStatus | undefined,
    }),
  });

  return (
    <div>
      <Subheader>{t('nav.admin_runs')}</Subheader>
      <Caption>{t('admin.runs.caption')}</Caption>

      <div className="card mb-4 flex flex-wrap gap-3 items-end">
        <div>
          <label className="label">user_id</label>
          <input className="input w-72 font-mono" value={userId} onChange={(e) => setUserId(e.target.value)} />
        </div>
        <div>
          <label className="label">{t('table.status')}</label>
          <select className="input w-40" value={status} onChange={(e) => setStatus(e.target.value as any)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s ? t(`status.${s}`) : t('admin.status_all')}</option>)}
          </select>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="df">
          <thead>
            <tr>
              <th>{t('table.ticker')}</th>
              <th>{t('table.trade_date')}</th>
              <th>{t('table.status')}</th>
              <th>{t('table.created_at')}</th>
              <th>{t('table.finished_at')}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {q.data?.map((r) => (
              <tr key={r.run_id}>
                <td className="font-mono">{r.ticker}</td>
                <td>{r.trade_date}</td>
                <td><StatusBadge status={r.status} /></td>
                <td className="text-muted">{r.created_at}</td>
                <td className="text-muted">{r.finished_at ?? '—'}</td>
                <td><Link to={`/analysis/${r.run_id}`} className="text-[#ff4b4b]">{t('table.details')}</Link></td>
              </tr>
            ))}
            {q.data?.length === 0 && (
              <tr><td colSpan={6} className="py-4 text-muted text-center">{t('table.no_matches')}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
