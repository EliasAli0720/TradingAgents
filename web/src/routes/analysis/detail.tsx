import { useParams } from 'react-router-dom';
import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { runsApi } from '@/api/runs';
import { useRunEvents } from '@/hooks/useRunEvents';
import { useAuth } from '@/hooks/useAuth';
import { Subheader, ErrorBox } from '@/components/ui/Page';
import { StatusBadge } from './list';
import { t } from '@/i18n';
import DecisionCard from '@/components/run/DecisionCard';
import AgentReportTabs, { type ReportMap } from '@/components/run/AgentReportTabs';
import RunProgress from '@/components/run/RunProgress';

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
  if (run.error || !run.data) return <ErrorBox>{t('analysis.not_found')}</ErrorBox>;

  const r = run.data;
  const active = r.status === 'queued' || r.status === 'running';
  const reports = (result.data?.reports ?? {}) as ReportMap;

  return (
    <div>
      <Subheader>{r.ticker} · {r.trade_date}</Subheader>

      <div className="card flex items-center justify-between mb-4">
        <div>
          <div className="text-sm text-muted">
            {t('analysis.asset_summary', {
              asset: r.asset_type === 'crypto' ? t('analysis.asset.crypto') : t('analysis.asset.stock'),
              count: r.analysts.length,
            })}
          </div>
          <div className="text-sm mt-1 flex items-center gap-2">
            {t('analysis.status')}<StatusBadge status={r.status} />
          </div>
        </div>
        {canOperate && active && (
          <button className="btn-danger" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
            {t('analysis.cancel_run')}
          </button>
        )}
      </div>

      {r.status === 'succeeded' && (
        <DecisionCard
          inputs={{
            decision: result.data?.decision,
            final_trade_decision: typeof reports.final_trade_decision === 'string' ? reports.final_trade_decision : undefined,
            trader_investment_plan: typeof reports.trader_investment_plan === 'string' ? reports.trader_investment_plan : undefined,
          }}
        />
      )}

      {r.status === 'succeeded' ? (
        result.isLoading ? (
          <div className="text-muted text-sm">{t('analysis.loading_result')}</div>
        ) : result.data ? (
          <AgentReportTabs reports={reports} />
        ) : (
          <ErrorBox>{t('analysis.result_failed')}</ErrorBox>
        )
      ) : (
        <>
          <RunProgress status={r.status} events={events} currentStep={r.current_step} />
          {r.status === 'failed' && r.error && (
            <>
              <Subheader>{t('analysis.failure_reason')}</Subheader>
              <ErrorBox>
                <div className="text-sm">{t('analysis.failure_message')}</div>
                <div className="text-xs text-muted mt-2 whitespace-pre-wrap">{r.error}</div>
              </ErrorBox>
            </>
          )}
        </>
      )}
    </div>
  );
}
