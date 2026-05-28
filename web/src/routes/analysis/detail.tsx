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

const LIVE_STATUSES = new Set(['queued', 'dispatching', 'running', 'cancelling']);

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
      return s && LIVE_STATUSES.has(s) ? 3000 : false;
    },
  });

  const { events, terminated } = useRunEvents(runId);

  useEffect(() => {
    if (terminated) {
      qc.invalidateQueries({ queryKey: ['run', runId] });
      qc.invalidateQueries({ queryKey: ['runResult', runId] });
      qc.invalidateQueries({ queryKey: ['runArtifacts', runId] });
    }
  }, [terminated, qc, runId]);

  const result = useQuery({
    queryKey: ['runResult', runId],
    queryFn: () => runsApi.result(runId!),
    enabled: !!runId && run.data?.status === 'succeeded',
  });

  const artifacts = useQuery({
    queryKey: ['runArtifacts', runId],
    queryFn: () => runsApi.artifacts(runId!),
    enabled: !!runId && run.data?.status === 'succeeded',
  });

  const cancel = useMutation({
    mutationFn: () => runsApi.cancel(runId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['run', runId] }),
  });

  if (run.isLoading) return <div className="text-muted">{t('common.loading')}</div>;
  if (run.error || !run.data) return <ErrorBox>{t('analysis.not_found')}</ErrorBox>;

  const r = run.data;
  const cancellable = r.status === 'queued' || r.status === 'dispatching' || r.status === 'running';
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
        {canOperate && cancellable && (
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

      {r.status === 'succeeded' && (
        <ArtifactList runId={r.run_id} artifacts={artifacts.data ?? []} loading={artifacts.isLoading} error={artifacts.isError} />
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
          <RunProgress status={r.status} events={events} currentStep={r.current_step} queuePosition={r.queue_position} />
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

function ArtifactList({
  runId,
  artifacts,
  loading,
  error,
}: {
  runId: string;
  artifacts: { artifact_id: string; kind: string; content_type: string | null; size_bytes: number; created_at: string }[];
  loading: boolean;
  error: boolean;
}) {
  if (loading) return <div className="card mb-4 text-sm text-muted">{t('common.loading')}</div>;
  if (error) return <ErrorBox>{t('analysis.artifacts_failed')}</ErrorBox>;

  return (
    <div className="card mb-4">
      <div className="text-sm font-semibold mb-3">{t('analysis.artifacts')}</div>
      {artifacts.length === 0 ? (
        <div className="text-sm text-muted">{t('analysis.artifacts_empty')}</div>
      ) : (
        <div className="space-y-2">
          {artifacts.map((artifact) => (
            <a
              key={artifact.artifact_id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border px-3 py-2 hover:border-[#ff4b4b]/70"
              href={runsApi.artifactUrl(runId, artifact.artifact_id)}
              target="_blank"
              rel="noreferrer"
            >
              <span>
                <span className="font-medium">{artifact.kind}</span>
                <span className="ml-2 text-xs text-muted font-mono">{artifact.artifact_id}</span>
              </span>
              <span className="text-xs text-muted">{formatBytes(artifact.size_bytes)}</span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
