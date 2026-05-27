import { useParams } from 'react-router-dom';
import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { runsApi } from '@/api/runs';
import { useRunEvents } from '@/hooks/useRunEvents';
import { useAuth } from '@/hooks/useAuth';
import { Subheader, ErrorBox } from '@/components/ui/Page';
import { StatusBadge } from './list';
import { t } from '@/i18n';

const SIGNAL_COLORS: Record<string, { fg: string; bg: string }> = {
  BUY:          { fg: '#4CAF50', bg: '#1b2a1d' },
  OVERWEIGHT:   { fg: '#2196F3', bg: '#102538' },
  HOLD:         { fg: '#37474F', bg: '#1c2126' },
  UNDERWEIGHT:  { fg: '#FFB300', bg: '#2a2417' },
  SELL:         { fg: '#F44336', bg: '#2a1818' },
};

export default function AnalysisDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const qc = useQueryClient();
  const { canOperate } = useAuth();

  const run = useQuery({
    queryKey: ['run', runId],
    queryFn: () => runsApi.get(runId!),
    enabled: !!runId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s && (s === 'queued' || s === 'running') ? 3000 : false;
    },
  });

  const { events, terminated } = useRunEvents(runId);

  useEffect(() => {
    if (terminated) {
      qc.invalidateQueries({ queryKey: ['run', runId] });
      qc.invalidateQueries({ queryKey: ['runResult', runId] });
    }
  }, [terminated, qc, runId]);

  const result = useQuery({
    queryKey: ['runResult', runId],
    queryFn: () => runsApi.result(runId!),
    enabled: !!runId && run.data?.status === 'succeeded',
  });

  const cancel = useMutation({
    mutationFn: () => runsApi.cancel(runId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['run', runId] }),
  });

  if (run.isLoading) return <div className="text-muted">{t('common.loading')}</div>;
  if (run.error || !run.data) return <ErrorBox>任务不存在或无权访问</ErrorBox>;

  const r = run.data;
  const active = r.status === 'queued' || r.status === 'running';
  const sig = (result.data?.decision ?? '').toUpperCase();
  const sigColor = SIGNAL_COLORS[sig];

  return (
    <div>
      <Subheader>{r.ticker} · {r.trade_date}</Subheader>

      <div className="card flex items-center justify-between mb-4">
        <div>
          <div className="text-sm text-muted">run_id: <span className="font-mono">{r.run_id}</span></div>
          <div className="text-sm mt-1">
            状态：<StatusBadge status={r.status} />
            {r.current_step && <span className="ml-2 text-muted">step: {r.current_step}</span>}
          </div>
        </div>
        {canOperate && active && (
          <button className="btn-danger" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
            取消任务
          </button>
        )}
      </div>

      {sigColor && (
        <div
          className="rounded-md mb-4 px-4 py-3 border-2"
          style={{ background: sigColor.bg, borderColor: sigColor.fg }}
        >
          <span className="text-xs uppercase tracking-widest text-muted">最终信号</span>
          <div className="text-2xl font-bold" style={{ color: sigColor.fg }}>{sig}</div>
        </div>
      )}

      <Subheader>实时事件（SSE）</Subheader>
      <div className="card">
        <pre className="text-xs max-h-72 overflow-auto font-mono whitespace-pre-wrap">
{events.length === 0 ? '（等待事件…）' : events.map((e) => `${e.event}  ${JSON.stringify(e.data)}`).join('\n')}
        </pre>
      </div>

      {r.status === 'failed' && r.error && (
        <>
          <Subheader>失败原因</Subheader>
          <ErrorBox><pre className="text-xs whitespace-pre-wrap">{r.error}</pre></ErrorBox>
        </>
      )}

      {r.status === 'succeeded' && (
        <>
          <Subheader>分析结果</Subheader>
          {result.isLoading ? (
            <div className="text-muted text-sm">加载结果…</div>
          ) : result.data ? (
            <div className="card">
              <pre className="text-xs max-h-96 overflow-auto whitespace-pre-wrap">
{JSON.stringify(result.data.reports, null, 2)}
              </pre>
            </div>
          ) : (
            <ErrorBox>结果加载失败</ErrorBox>
          )}
        </>
      )}
    </div>
  );
}
