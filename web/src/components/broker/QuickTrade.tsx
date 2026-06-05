import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { brokerApi, type PreviewResult } from '@/api/broker';
import { isDesktop } from '@/api/brokerChannel';
import { brokerNotConnectedError } from '@/api/brokerReadiness';
import { manualTradeRoute } from '@/api/manualTradeFlow';
import { useBrokerConnection } from '@/hooks/useBrokerConnection';
import { useAuth } from '@/hooks/useAuth';
import { getLocale, t } from '@/i18n';

type Side = 'buy' | 'sell';
type OType = 'market' | 'limit';

function money(n: number | null | undefined): string {
  return n == null ? '—' : n.toLocaleString(getLocale(), { maximumFractionDigits: 2 });
}

// Manual quick order. Webull places through the server broker; desktop IBKR
// places through the local sidecar, then mirrors the order to the server.
export default function QuickTrade() {
  const { channel, status } = useBrokerConnection();
  const { canOperate } = useAuth();
  const qc = useQueryClient();
  const desktop = isDesktop();

  const serverStatus = useQuery({
    queryKey: ['broker', 'status', 'server'],
    queryFn: () => brokerApi.status(),
    enabled: desktop,
    refetchInterval: 30000,
    retry: 1,
  });

  const [ticker, setTicker] = useState('');
  const [side, setSide] = useState<Side>('buy');
  const [qty, setQty] = useState(1);
  const [orderType, setOrderType] = useState<OType>('market');
  const [limitPrice, setLimitPrice] = useState<number | ''>('');
  const [preview, setPreview] = useState<PreviewResult | null>(null);

  const activeServerStatus = desktop ? serverStatus.data : status;
  const route = manualTradeRoute({
    desktop,
    serverStatus: activeServerStatus,
    serverStatusLoading: desktop && serverStatus.isLoading,
    localStatus: desktop ? status : null,
    localCanExecute: typeof channel.execute === 'function',
  });
  const accountId = route === 'server' ? (activeServerStatus?.account_id ?? '') : (status?.account_id ?? '');
  const canPreview = route === 'server' || (route === 'local' && typeof channel.preview === 'function');
  const canExecute = route === 'server' || (route === 'local' && typeof channel.execute === 'function');
  const valid =
    ticker.trim().length > 0 &&
    qty > 0 &&
    (orderType === 'market' || (typeof limitPrice === 'number' && limitPrice > 0));

  const req = () => ({
    ticker: ticker.trim().toUpperCase(),
    qty,
    side,
    order_type: orderType,
    limit_price: orderType === 'limit' && typeof limitPrice === 'number' ? limitPrice : undefined,
    time_in_force: 'day',
  });

  const previewMut = useMutation({
    mutationFn: () => {
      if (route === 'server') return brokerApi.previewOrder(req());
      if (route === 'local' && channel.preview) return channel.preview(req());
      throw brokerNotConnectedError();
    },
    onSuccess: (r) => setPreview(r),
  });

  const placeMut = useMutation({
    mutationFn: async () => {
      if (route === 'server') {
        return brokerApi.placeOrder(req());
      }
      if (route !== 'local' || !channel.execute) {
        throw brokerNotConnectedError();
      }
      if (!accountId) {
        throw brokerNotConnectedError();
      }
      const placed = await channel.execute!(req());
      await brokerApi.recordManualOrder({
        broker_order_id: placed.broker_order_id,
        account_id: accountId,
        broker: status?.broker ?? 'ibkr',
        ticker: placed.ticker,
        side: placed.side,
        order_type: placed.order_type,
        quantity: placed.quantity,
        status: placed.status,
        filled_qty: placed.filled_qty,
        filled_avg_price: placed.filled_avg_price,
        limit_price: placed.limit_price,
      });
      return placed;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['broker'] });
      qc.invalidateQueries({ queryKey: ['trades'] });
      qc.invalidateQueries({ queryKey: ['perf'] });
      setPreview(null);
    },
  });

  const onSubmit = () => {
    if (!valid) return;
    const ok = window.confirm(
      t('qt.confirm', { side: t(`qt.side.${side}`), qty, ticker: ticker.trim().toUpperCase() }),
    );
    if (ok) placeMut.mutate();
  };

  const disabledReason = desktop && serverStatus.isLoading
    ? t('common.loading')
    : !canOperate
      ? t('qt.need_operator')
      : !canExecute
        ? t('qt.connect_first')
        : null;

  return (
    <div>
      <div className="font-semibold mb-2">{t('qt.header')}</div>
      <div className={`space-y-2 ${disabledReason ? 'opacity-60' : ''}`}>
        <input
          className="input"
          placeholder={t('qt.ticker')}
          value={ticker}
          disabled={!!disabledReason}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
        />
        <div className="flex gap-2">
          <select
            className="input"
            value={side}
            disabled={!!disabledReason}
            onChange={(e) => setSide(e.target.value as Side)}
          >
            <option value="buy">{t('qt.side.buy')}</option>
            <option value="sell">{t('qt.side.sell')}</option>
          </select>
          <select
            className="input"
            value={orderType}
            disabled={!!disabledReason}
            onChange={(e) => setOrderType(e.target.value as OType)}
          >
            <option value="market">{t('qt.type.market')}</option>
            <option value="limit">{t('qt.type.limit')}</option>
          </select>
        </div>
        <input
          className="input"
          type="number"
          min={1}
          placeholder={t('qt.qty')}
          value={qty}
          disabled={!!disabledReason}
          onChange={(e) => setQty(Math.max(0, Math.floor(Number(e.target.value))))}
        />
        {orderType === 'limit' && (
          <input
            className="input"
            type="number"
            step="0.01"
            placeholder={t('qt.limit_price')}
            value={limitPrice}
            disabled={!!disabledReason}
            onChange={(e) => setLimitPrice(e.target.value === '' ? '' : Number(e.target.value))}
          />
        )}

        <div className="flex gap-2">
          <button
            className="btn-ghost btn-block"
            disabled={!!disabledReason || !valid || !canPreview || previewMut.isPending}
            onClick={() => previewMut.mutate()}
          >
            {previewMut.isPending ? t('qt.previewing') : t('qt.preview')}
          </button>
          <button
            className="btn-primary btn-block"
            disabled={!!disabledReason || !valid || placeMut.isPending}
            onClick={onSubmit}
          >
            {placeMut.isPending ? t('qt.placing') : t('qt.submit')}
          </button>
        </div>

        {preview && (
          <div className="text-xs text-muted space-y-0.5">
            <div>{t('qt.est_margin')}: {money(preview.init_margin)}</div>
            <div>{t('qt.est_commission')}: {money(preview.commission)}</div>
            {preview.warning && <div className="text-warn">{preview.warning}</div>}
          </div>
        )}
        {placeMut.isSuccess && placeMut.data && (
          <div className="text-xs text-success">
            {t('qt.placed', { id: placeMut.data.broker_order_id, status: placeMut.data.status })}
          </div>
        )}
        {(placeMut.isError || previewMut.isError) && (
          <div className="text-xs text-danger">
            {((placeMut.error || previewMut.error) as { detail?: string; message?: string })?.detail ||
              ((placeMut.error || previewMut.error) as { message?: string })?.message ||
              t('qt.failed')}
          </div>
        )}
        {disabledReason && <div className="text-xs text-muted">{disabledReason}</div>}
      </div>
    </div>
  );
}
