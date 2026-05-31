import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { brokerApi } from '@/api/broker';
import { useAuth } from '@/hooks/useAuth';
import { Subheader, Caption, ErrorBox } from '@/components/ui/Page';
import { getLocale, t } from '@/i18n';

function num(n: number | null, digits = 2): string {
  return n == null ? '—' : n.toLocaleString(getLocale(), { maximumFractionDigits: digits });
}

function fmt(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(getLocale(), { hour12: false });
  } catch {
    return iso;
  }
}

const STATUS_CLS: Record<string, string> = {
  pending: 'bg-warnBg text-warn',
  partially_filled: 'bg-infoBg text-info',
  filled: 'bg-successBg text-success',
  cancelled: 'bg-neutralBg text-muted',
  rejected: 'bg-dangerBg text-danger',
  expired: 'bg-neutralBg text-muted',
};

const OPEN_STATUSES = new Set(['pending', 'partially_filled']);

export default function BrokerOrdersPage() {
  const { canOperate } = useAuth();
  const qc = useQueryClient();

  const orders = useQuery({
    queryKey: ['broker', 'orders'],
    queryFn: brokerApi.orders,
    refetchInterval: 10000,
  });
  const cancel = useMutation({
    mutationFn: brokerApi.cancel,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['broker', 'orders'] }),
  });

  return (
    <div>
      <Subheader>{t('broker.orders.title')}</Subheader>
      <Caption>{t('broker.orders.caption')}</Caption>

      {orders.isLoading ? (
        <div className="text-muted">{t('common.loading')}</div>
      ) : orders.error ? (
        <ErrorBox>{t('common.load_failed')}</ErrorBox>
      ) : (
        <div className="card overflow-x-auto">
          <table className="df">
            <thead>
              <tr>
                <th>{t('table.ticker')}</th>
                <th>{t('table.side')}</th>
                <th>{t('table.order_type')}</th>
                <th>{t('table.qty')}</th>
                <th>{t('table.filled')}</th>
                <th>{t('table.avg_price')}</th>
                <th>{t('table.status')}</th>
                <th>{t('table.updated_at')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {orders.data?.map((o) => (
                <tr key={o.broker_order_id}>
                  <td className="font-mono">{o.ticker}</td>
                  <td className={o.side.toUpperCase() === 'BUY' ? 'text-success' : 'text-danger'}>
                    {o.side.toUpperCase()}
                  </td>
                  <td>{o.order_type}</td>
                  <td>{o.quantity}</td>
                  <td>{o.filled_qty}</td>
                  <td>{num(o.filled_avg_price)}</td>
                  <td>
                    <span className={`badge ${STATUS_CLS[o.status] ?? 'bg-white/10'}`}>{o.status}</span>
                  </td>
                  <td className="text-muted">{fmt(o.updated_at)}</td>
                  <td>
                    {canOperate && OPEN_STATUSES.has(o.status) ? (
                      <button
                        className="btn-ghost"
                        disabled={cancel.isPending}
                        onClick={() => cancel.mutate(o.broker_order_id)}
                      >
                        {t('broker.action.cancel')}
                      </button>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
              {orders.data?.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-4 text-muted text-center">{t('common.empty')}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
