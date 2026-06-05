import { useParams, Link } from 'react-router-dom';
import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { runsApi, type RunResult } from '@/api/runs';
import { brokerApi } from '@/api/broker';
import { getBrokerChannel, isDesktop } from '@/api/brokerChannel';
import { isUsableBrokerStatus, shouldUseServerProposal } from '@/api/brokerReadiness';
import { createProposal } from '@/api/tradeFlow';
import { useRunEvents } from '@/hooks/useRunEvents';
import { useAuth } from '@/hooks/useAuth';
import { Subheader, ErrorBox, Info } from '@/components/ui/Page';
import { StatusBadge } from './list';
import { t, getLang } from '@/i18n';
import DecisionCard from '@/components/run/DecisionCard';
import AgentReportTabs, { type ReportMap } from '@/components/run/AgentReportTabs';
import RunProgress from '@/components/run/RunProgress';
import { proposalButtonLabelKey, proposalEligibility } from './proposalEligibility';

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
    // Translations stream in section-by-section after the run succeeds, so
    // poll until EVERY section has a translation for the current language —
    // not just the first — otherwise some tabs would stay untranslated until
    // a manual refresh. English needs no polling.
    refetchInterval: (q) => {
      const lang = getLang();
      if (lang === 'en') return false;
      const data = q.state.data;
      if (!data) return false;
      return translationComplete(data, lang) ? false : 4000;
    },
  });

  const brokerStatusEnabled = canOperate && run.data?.status === 'succeeded';
  const desktop = isDesktop();
  const serverBrokerStatus = useQuery({
    queryKey: ['broker', 'status', 'server'],
    queryFn: () => brokerApi.status(),
    enabled: brokerStatusEnabled,
    refetchInterval: 30000,
    retry: 1,
  });
  const localBrokerStatus = useQuery({
    queryKey: ['broker', 'status', 'local'],
    queryFn: () => getBrokerChannel().status(),
    enabled: brokerStatusEnabled && desktop,
    refetchInterval: 5000,
    retry: 1,
  });

  const cancel = useMutation({
    mutationFn: () => runsApi.cancel(runId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['run', runId] }),
  });

  const propose = useMutation({
    mutationFn: () => createProposal(runId!, run.data!.ticker),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['broker', 'approvals'] }),
  });

  if (run.isLoading) return <div className="text-muted">{t('common.loading')}</div>;
  if (run.error || !run.data) return <ErrorBox>{t('analysis.not_found')}</ErrorBox>;

  const r = run.data;
  const cancellable = r.status === 'queued' || r.status === 'dispatching' || r.status === 'running';
  const reports = (result.data?.reports ?? {}) as ReportMap;
  const proposal = proposalEligibility({
    canOperate,
    runStatus: r.status,
    decision: result.data?.decision,
    brokerStatusLoading:
      brokerStatusEnabled &&
      (serverBrokerStatus.isLoading ||
        (desktop && !shouldUseServerProposal(serverBrokerStatus.data) && localBrokerStatus.isLoading)),
    hasUsableBrokerAccount: desktop
      ? shouldUseServerProposal(serverBrokerStatus.data) || isUsableBrokerStatus(localBrokerStatus.data)
      : isUsableBrokerStatus(serverBrokerStatus.data),
  });
  const proposalError = propose.error as { detail?: string } | null;
  const proposalErrorDetail =
    proposalError?.detail === 'broker_not_connected'
      ? t('broker.proposal.connect_account_hint')
      : proposalError?.detail;

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

      {proposal.state !== 'hidden' && (
        <div className="mb-4 flex items-center gap-3">
          {proposal.state === 'waiting' && (
            <button className="btn-primary" disabled>
              {t('common.loading')}
            </button>
          )}
          {proposal.state === 'actionable' && (
            <button className="btn-primary" disabled={propose.isPending} onClick={() => propose.mutate()}>
              {t(proposalButtonLabelKey(propose.isPending))}
            </button>
          )}
          {proposal.state === 'connect_account' && (
            <>
              <Info>{t('broker.proposal.connect_account_hint')}</Info>
              <Link to="/broker" className="btn-primary">
                {t('broker.proposal.connect_account')}
              </Link>
            </>
          )}
          {proposal.state === 'no_action' && (
            <Info>{t('broker.proposal.no_action', { signal: proposal.signal || 'HOLD' })}</Info>
          )}
          {propose.isSuccess && (
            <span className="text-sm text-success">
              {t('broker.proposal.created')}{' '}
              <Link to="/broker/approvals" className="text-brandGold">{t('nav.approvals')}</Link>
            </span>
          )}
          {propose.isError && (
            <span className="text-sm text-danger">
              {t('broker.proposal.failed')}: {proposalErrorDetail}
            </span>
          )}
        </div>
      )}

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
          <>
            {getLang() !== 'en' && !translationComplete(result.data, getLang()) && (
              <div className="text-xs text-muted mb-2">{t('report.translating')}</div>
            )}
            <AgentReportTabs reports={reports} reportsI18n={result.data.reports_i18n} />
          </>
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

// True when every non-empty English report section has a translation for
// `lang` (or when lang is English, which needs none). Drives both the poll
// stop condition and the "translating" hint.
function translationComplete(data: RunResult, lang: string): boolean {
  if (lang === 'en') return true;
  const translated = data.reports_i18n?.[lang] ?? {};
  const expected = Object.entries(data.reports ?? {})
    .filter(([, v]) => typeof v === 'string' && (v as string).trim().length > 0)
    .map(([k]) => k);
  return expected.every((k) => typeof translated[k] === 'string');
}
