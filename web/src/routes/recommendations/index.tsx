import { Link } from 'react-router-dom';
import type { Dispatch, SetStateAction } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  recommendationsApi,
  type RecommendationBatch,
  type RecommendationBatchSummary,
} from '@/api/recommendations';
import type { ApiError } from '@/api/client';
import { Subheader, Caption, ErrorBox } from '@/components/ui/Page';
import { getLocale, t } from '@/i18n';

function splitTickers(value: string): string[] {
  return value
    .split(/[\s,]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function fmtTime(iso: string): string {
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
    enabled: Boolean(activeBatchId),
  });

  useEffect(() => {
    if (watchlist.data) setWatchlistText(watchlist.data.tickers.join(', '));
  }, [watchlist.data]);

  useEffect(() => {
    if (!activeBatchId && batches.data?.[0]) setActiveBatchId(batches.data[0].batch_id);
  }, [activeBatchId, batches.data]);

  const saveWatchlist = useMutation({
    mutationFn: () => recommendationsApi.saveWatchlist(splitTickers(watchlistText)),
    onSuccess: (saved) => {
      setWatchlistText(saved.tickers.join(', '));
      qc.setQueryData(['recommendations', 'watchlist'], saved);
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
    () => Object.entries(selected).filter(([, value]) => value).map(([id]) => id),
    [selected],
  );
  const error = (
    watchlist.error ||
    batches.error ||
    activeBatch.error ||
    saveWatchlist.error ||
    generate.error ||
    analyze.error
  ) as unknown as ApiError | undefined;

  return (
    <div className="space-y-4">
      <div>
        <Subheader>{t('recommendations.title')}</Subheader>
        <Caption>{t('recommendations.caption')}</Caption>
      </div>

      <section className="card space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className="font-semibold">{t('recommendations.watchlist')}</div>
          {watchlist.data?.updated_at && (
            <div className="text-xs text-muted">{fmtTime(watchlist.data.updated_at)}</div>
          )}
        </div>
        <textarea
          className="input min-h-24 font-mono"
          value={watchlistText}
          onChange={(e) => setWatchlistText(e.target.value)}
          placeholder={t('recommendations.watchlist_placeholder')}
        />
        <div className="flex justify-end">
          <button
            type="button"
            className="btn-ghost"
            disabled={saveWatchlist.isPending}
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
            {analyze.isPending ? t('recommendations.analyzing') : t('recommendations.start_analysis')}
          </button>
        )}
      </section>

      {error && (
        <ErrorBox>
          <span>{error.status} - {error.detail}</span>
          {error.status === 409 && error.detail === 'model settings not configured' && (
            <Link to="/settings/model" className="text-[#ff4b4b] ml-2">
              {t('recommendations.model_required')}
            </Link>
          )}
        </ErrorBox>
      )}

      {analyze.data && (
        <section className="card text-sm space-y-2">
          {analyze.data.created.length > 0 && (
            <div>
              <div className="font-semibold mb-1">{t('recommendations.created_runs')}</div>
              {analyze.data.created.map((row) => (
                <div key={row.item_id} className="text-success">
                  {row.ticker} - <Link to={`/analysis/${row.run_id}`} className="text-[#ff4b4b]">{row.run_id}</Link>
                </div>
              ))}
            </div>
          )}
          {analyze.data.failed.length > 0 && (
            <div>
              <div className="font-semibold mb-1">{t('recommendations.failed_items')}</div>
              {analyze.data.failed.map((row) => (
                <div key={row.item_id} className="text-danger">
                  {row.ticker ?? row.item_id}: {row.detail}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-4">
        <CurrentBatch batch={batch} selected={selected} setSelected={setSelected} />
        <History
          batches={batches.data ?? []}
          activeBatchId={activeBatchId}
          setActiveBatchId={(id) => {
            setSelected({});
            setActiveBatchId(id);
          }}
        />
      </div>
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
  if (!batch) return <div className="card text-muted text-sm">{t('recommendations.no_batch')}</div>;
  return (
    <section className="card overflow-x-auto">
      <div className="font-semibold mb-3">{t('recommendations.current_batch')}</div>
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
                  disabled={item.status !== 'recommended'}
                  checked={Boolean(selected[item.item_id])}
                  onChange={(e) => setSelected((s) => ({ ...s, [item.item_id]: e.target.checked }))}
                />
              </td>
              <td>
                <div className="font-mono font-semibold">{item.ticker}</div>
                <div className="text-xs text-muted">{t(`recommendations.source.${item.source}`)}</div>
              </td>
              <td>{item.priority}</td>
              <td className="min-w-56">{item.reason}</td>
              <td className="min-w-48">{item.risk}</td>
              <td>{item.status}</td>
              <td>
                {item.run_id ? (
                  <Link to={`/analysis/${item.run_id}`} className="text-[#ff4b4b]">
                    {item.run_id}
                  </Link>
                ) : (
                  '-'
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function History({
  batches,
  activeBatchId,
  setActiveBatchId,
}: {
  batches: RecommendationBatchSummary[];
  activeBatchId: string | null;
  setActiveBatchId: (id: string) => void;
}) {
  return (
    <section className="card">
      <div className="font-semibold mb-3">{t('recommendations.history')}</div>
      <div className="space-y-2">
        {batches.map((batch) => (
          <button
            type="button"
            key={batch.batch_id}
            className={`btn-ghost btn-block justify-start ${activeBatchId === batch.batch_id ? 'border-[#ff4b4b]' : ''}`}
            onClick={() => setActiveBatchId(batch.batch_id)}
          >
            <span className="text-left">
              <span className="block font-mono text-xs">{batch.batch_id}</span>
              <span className="block text-xs text-muted">{fmtTime(batch.created_at)} - {batch.item_count}</span>
            </span>
          </button>
        ))}
        {batches.length === 0 && <div className="text-sm text-muted">{t('common.empty')}</div>}
      </div>
    </section>
  );
}
