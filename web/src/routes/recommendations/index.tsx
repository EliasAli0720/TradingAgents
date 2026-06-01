import { Link } from 'react-router-dom';
import type { Dispatch, SetStateAction } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  recommendationsApi,
  type RecommendationBatch,
  type RecommendationBatchSummary,
  type RecommendationItem,
  type RecommendationItemStatus,
  type RunStatus,
} from '@/api/recommendations';
import type { ApiError } from '@/api/client';
import { Subheader, Caption, ErrorBox } from '@/components/ui/Page';
import { getLocale, t } from '@/i18n';

const STATUS_CLS: Record<RecommendationItemStatus, string> = {
  recommended: 'bg-infoBg text-info',
  analysis_queued: 'bg-warnBg text-warn',
  analysis_failed: 'bg-dangerBg text-danger',
  ignored: 'bg-neutralBg text-muted',
};

const RUN_STATUS_CLS: Record<RunStatus, string> = {
  queued: 'bg-warnBg text-warn',
  dispatching: 'bg-warnBg text-warn',
  running: 'bg-infoBg text-info',
  succeeded: 'bg-successBg text-success',
  failed: 'bg-dangerBg text-danger',
  cancelled: 'bg-neutralBg text-muted',
};

const LIVE_RUN_STATUSES: ReadonlySet<RunStatus> = new Set([
  'queued',
  'dispatching',
  'running',
]);

// An item is "settled" once it has no in-flight run: never analyzed, or its run
// reached a terminal state. Such items are selectable (analyze / re-analyze).
function isSelectable(item: RecommendationItem): boolean {
  if (item.status === 'recommended' || item.status === 'analysis_failed') return true;
  return item.run_status != null && !LIVE_RUN_STATUSES.has(item.run_status);
}

function splitTickers(value: string): string[] {
  return value
    .split(/[\s,]+/)
    .map((part) => part.trim().toUpperCase())
    .filter(Boolean);
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(getLocale(), { hour12: false });
  } catch {
    return iso;
  }
}

export default function RecommendationsPage() {
  const qc = useQueryClient();
  const [watchlistText, setWatchlistText] = useState('');
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);

  const watchlist = useQuery({
    queryKey: ['recommendations', 'watchlist'],
    queryFn: recommendationsApi.watchlist,
  });
  const batches = useQuery({
    queryKey: ['recommendations', 'batches'],
    queryFn: recommendationsApi.batches,
  });
  const activeBatch = useQuery({
    queryKey: ['recommendations', 'batch', activeBatchId],
    queryFn: () => recommendationsApi.batch(activeBatchId!),
    enabled: !!activeBatchId,
    // Poll while any item still has an in-flight run so the page reflects
    // queued → running → succeeded/failed instead of staying stuck.
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      const anyLive = items.some(
        (item) => item.run_status != null && LIVE_RUN_STATUSES.has(item.run_status),
      );
      return anyLive ? 4000 : false;
    },
  });

  useEffect(() => {
    if (watchlist.data) setWatchlistText(watchlist.data.tickers.join(', '));
  }, [watchlist.data]);

  useEffect(() => {
    if (!activeBatchId && batches.data?.[0]) setActiveBatchId(batches.data[0].batch_id);
  }, [activeBatchId, batches.data]);

  useEffect(() => {
    setSelected({});
  }, [activeBatchId]);

  const saveWatchlist = useMutation({
    mutationFn: () => recommendationsApi.saveWatchlist(splitTickers(watchlistText)),
    onSuccess: (saved) => {
      qc.setQueryData(['recommendations', 'watchlist'], saved);
      qc.invalidateQueries({ queryKey: ['recommendations', 'watchlist'] });
    },
  });

  const generate = useMutation({
    mutationFn: recommendationsApi.generate,
    onSuccess: (batch) => {
      setActiveBatchId(batch.batch_id);
      setSelected({});
      qc.invalidateQueries({ queryKey: ['recommendations', 'batches'] });
      qc.setQueryData(['recommendations', 'batch', batch.batch_id], batch);
    },
  });

  const analyze = useMutation({
    mutationFn: (itemIds: string[]) => recommendationsApi.analyze(activeBatchId!, itemIds),
    onSuccess: () => {
      setSelected({});
      qc.invalidateQueries({ queryKey: ['recommendations', 'batches'] });
      qc.invalidateQueries({ queryKey: ['recommendations', 'batch', activeBatchId] });
    },
  });

  const batch = activeBatch.data;
  const selectedIds = useMemo(
    () =>
      Object.entries(selected)
        .filter(([, value]) => value)
        .map(([id]) => id),
    [selected],
  );
  const actionError = (saveWatchlist.error || generate.error || analyze.error) as
    unknown as ApiError | undefined;

  return (
    <div className="space-y-4">
      <div>
        <Subheader>{t('recommendations.title')}</Subheader>
        <Caption>{t('recommendations.caption')}</Caption>
      </div>

      <section className="card space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className="font-semibold">{t('recommendations.watchlist')}</div>
          <div className="text-xs text-muted">
            {watchlist.data?.updated_at
              ? t('recommendations.updated_at', { time: fmtTime(watchlist.data.updated_at) })
              : t('recommendations.never_updated')}
          </div>
        </div>
        <textarea
          className="input min-h-24 font-mono"
          value={watchlistText}
          onChange={(e) => setWatchlistText(e.target.value)}
          placeholder="AAPL, MSFT, NVDA, TSLA, GOOGL"
        />
        <div className="flex items-center justify-between gap-3">
          <div className="text-xs text-muted">
            {saveWatchlist.isSuccess ? t('recommendations.saved') : t('recommendations.select_hint')}
          </div>
          <button
            type="button"
            className="btn-ghost"
            disabled={saveWatchlist.isPending || watchlist.isLoading}
            onClick={() => saveWatchlist.mutate()}
          >
            {t('recommendations.save_watchlist')}
          </button>
        </div>
      </section>

      <section className="flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          className="btn-primary"
          disabled={generate.isPending}
          onClick={() => generate.mutate()}
        >
          {generate.isPending ? t('recommendations.generating') : t('recommendations.generate')}
        </button>
        {batch && (
          <button
            type="button"
            className="btn-primary"
            disabled={!selectedIds.length || analyze.isPending}
            onClick={() => analyze.mutate(selectedIds)}
          >
            {t('recommendations.start_analysis')}
          </button>
        )}
      </section>

      {actionError && (
        <ErrorBox>
          {/* A 409 can mean either "no model" or "no watchlist" — show the
              message (and the model link) that actually matches the cause,
              instead of always pointing at model settings. */}
          {actionError.status === 409 && /model/i.test(actionError.detail ?? '') ? (
            <span>
              {t('recommendations.err_model_required')}
              <Link to="/settings/model" className="text-[#ff4b4b] ml-2">
                {t('analysis.configure_model')}
              </Link>
            </span>
          ) : actionError.status === 409 && /watchlist/i.test(actionError.detail ?? '') ? (
            <span>{t('recommendations.err_watchlist_required')}</span>
          ) : (
            <span>{actionError.status} · {actionError.detail}</span>
          )}
        </ErrorBox>
      )}

      {analyze.data && <AnalyzeResult response={analyze.data} />}

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-4">
        <div>
          <div className="font-semibold mb-3">{t('recommendations.current_batch')}</div>
          {activeBatch.isLoading ? (
            <div className="card text-sm text-muted">{t('common.loading')}</div>
          ) : activeBatch.error ? (
            <ErrorBox>{t('recommendations.batch_load_failed')}</ErrorBox>
          ) : (
            <CurrentBatch batch={batch} selected={selected} setSelected={setSelected} />
          )}
        </div>
        <History
          batches={batches.data ?? []}
          activeBatchId={activeBatchId}
          setActiveBatchId={setActiveBatchId}
          loading={batches.isLoading}
          error={Boolean(batches.error)}
        />
      </div>
    </div>
  );
}

function AnalyzeResult({ response }: { response: { created: { item_id: string; ticker: string; run_id: string }[]; failed: { item_id: string; ticker?: string | null; detail: string }[] } }) {
  return (
    <div className="card text-sm space-y-2">
      {response.created.length > 0 && (
        <div>
          <div className="font-semibold mb-1">{t('recommendations.created_runs')}</div>
          <div className="space-y-1">
            {response.created.map((row) => (
              <div key={row.item_id} className="text-success">
                <span className="font-mono">{row.ticker}</span>
                {' -> '}
                <Link to={`/analysis/${row.run_id}`} className="text-[#ff4b4b]">
                  {row.run_id}
                </Link>
              </div>
            ))}
          </div>
        </div>
      )}
      {response.failed.length > 0 && (
        <div>
          <div className="font-semibold mb-1 text-danger">{t('recommendations.partial_failures')}</div>
          <div className="space-y-1">
            {response.failed.map((row) => (
              <div key={row.item_id} className="text-danger">
                <span className="font-mono">{row.ticker ?? row.item_id}</span>: {row.detail}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function CurrentBatch({
  batch,
  selected,
  setSelected,
}: {
  batch?: RecommendationBatch;
  selected: Record<string, boolean>;
  setSelected: Dispatch<SetStateAction<Record<string, boolean>>>;
}) {
  if (!batch) return <div className="card text-muted text-sm">{t('common.empty')}</div>;

  return (
    <section className="card overflow-x-auto">
      <table className="df">
        <thead>
          <tr>
            <th></th>
            <th>{t('table.ticker')}</th>
            <th>{t('recommendations.priority')}</th>
            <th>{t('recommendations.reason')}</th>
            <th>{t('recommendations.risk')}</th>
            <th>{t('table.status')}</th>
            <th>{t('recommendations.run')}</th>
          </tr>
        </thead>
        <tbody>
          {batch.items.map((item) => (
            <tr key={item.item_id}>
              <td>
                <input
                  type="checkbox"
                  disabled={!isSelectable(item)}
                  checked={Boolean(selected[item.item_id])}
                  onChange={(e) => setSelected((s) => ({ ...s, [item.item_id]: e.target.checked }))}
                />
              </td>
              <td>
                <div className="font-mono font-semibold">{item.ticker}</div>
                <div className="text-xs text-muted">{t(`recommendations.source.${item.source}`)}</div>
              </td>
              <td>{item.priority}</td>
              <td className="min-w-64">{item.reason}</td>
              <td className="min-w-56">{item.risk}</td>
              <td>
                {/* Prefer the live run status once a run exists; fall back to
                    the item's own lifecycle status otherwise. Both are localized. */}
                {item.run_status ? (
                  <span className={`badge ${RUN_STATUS_CLS[item.run_status]}`}>
                    {t(`recommendations.run_status.${item.run_status}`)}
                  </span>
                ) : (
                  <span className={`badge ${STATUS_CLS[item.status]}`}>
                    {t(`recommendations.item_status.${item.status}`)}
                  </span>
                )}
                {item.error && <div className="text-xs text-danger mt-1">{item.error}</div>}
              </td>
              <td>
                {item.run_id ? (
                  <Link to={`/analysis/${item.run_id}`} className="text-[#ff4b4b]">
                    {item.run_id}
                  </Link>
                ) : (
                  <span className="text-muted">—</span>
                )}
              </td>
            </tr>
          ))}
          {batch.items.length === 0 && (
            <tr>
              <td colSpan={7} className="py-4 text-muted text-center">{t('common.empty')}</td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}

function History({
  batches,
  activeBatchId,
  setActiveBatchId,
  loading,
  error,
}: {
  batches: RecommendationBatchSummary[];
  activeBatchId: string | null;
  setActiveBatchId: (id: string) => void;
  loading: boolean;
  error: boolean;
}) {
  return (
    <section className="card">
      <div className="font-semibold mb-3">{t('recommendations.history')}</div>
      {loading ? (
        <div className="text-sm text-muted">{t('common.loading')}</div>
      ) : error ? (
        <div className="text-sm text-danger">{t('common.load_failed')}</div>
      ) : (
        <div className="space-y-2">
          {batches.map((batch) => (
            <button
              key={batch.batch_id}
              type="button"
              className={`btn-ghost btn-block justify-start ${activeBatchId === batch.batch_id ? 'border-[#ff4b4b]' : ''}`}
              onClick={() => setActiveBatchId(batch.batch_id)}
            >
              <span className="text-left min-w-0">
                <span className="block font-mono text-xs truncate">{batch.batch_id}</span>
                <span className="block text-xs text-muted">
                  {fmtTime(batch.created_at)} · {t('recommendations.item_count', { count: batch.item_count })}
                </span>
              </span>
            </button>
          ))}
          {batches.length === 0 && <div className="text-sm text-muted">{t('common.empty')}</div>}
        </div>
      )}
    </section>
  );
}
