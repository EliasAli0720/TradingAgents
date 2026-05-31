import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { brokerApi, type TradeApproval } from '@/api/broker';
import { approveProposal } from '@/api/tradeFlow';
import { useAuth } from '@/hooks/useAuth';
import { Subheader, Caption, ErrorBox } from '@/components/ui/Page';
import { getLocale, t } from '@/i18n';

function num(n: number | null, digits = 2): string {
  return n == null ? '—' : n.toLocaleString(getLocale(), { maximumFractionDigits: digits });
}

const STATUS_CLS: Record<string, string> = {
  pending: 'bg-warnBg text-warn',
  approved: 'bg-infoBg text-info',
  submitted: 'bg-successBg text-success',
  rejected: 'bg-neutralBg text-muted',
  failed: 'bg-dangerBg text-danger',
  expired: 'bg-neutralBg text-muted',
};

function riskReason(a: TradeApproval): string {
  const v = a.risk_verdict as { reason?: string } | null;
  return v?.reason ?? '—';
}

export default function BrokerApprovalsPage() {
  const { canOperate } = useAuth();
  const qc = useQueryClient();

  const approvals = useQuery({
    queryKey: ['broker', 'approvals'],
    queryFn: () => brokerApi.approvals(),
    refetchInterval: 10000,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['broker', 'approvals'] });
    qc.invalidateQueries({ queryKey: ['broker', 'orders'] });
  };

  const approve = useMutation({ mutationFn: (a: TradeApproval) => approveProposal(a), onSuccess: invalidate });
  const reject = useMutation({ mutationFn: brokerApi.reject, onSuccess: invalidate });
  const busy = approve.isPending || reject.isPending;
  const actionError = (approve.error || reject.error) as { detail?: string } | null;

  return (
    <div>
      <Subheader>{t('broker.approvals.title')}</Subheader>
      <Caption>{t('broker.approvals.caption')}</Caption>

      {actionError && <ErrorBox>{actionError.detail ?? t('common.load_failed')}</ErrorBox>}

      {approvals.isLoading ? (
        <div className="text-muted">{t('common.loading')}</div>
      ) : approvals.error ? (
        <ErrorBox>{t('common.load_failed')}</ErrorBox>
      ) : (
        <div className="card overflow-x-auto">
          <table className="df">
            <thead>
              <tr>
                <th>{t('table.ticker')}</th>
                <th>{t('table.side')}</th>
                <th>{t('table.qty')}</th>
                <th>{t('table.est_price')}</th>
                <th>{t('table.est_value')}</th>
                <th>{t('table.risk')}</th>
                <th>{t('table.status')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {approvals.data?.map((a) => (
                <tr key={a.approval_id}>
                  <td className="font-mono">{a.ticker}</td>
                  <td className={a.side === 'buy' ? 'text-success' : 'text-danger'}>{a.side.toUpperCase()}</td>
                  <td>{a.quantity}</td>
                  <td>{num(a.estimated_price)}</td>
                  <td>{num(a.estimated_value)}</td>
                  <td className="text-muted text-xs max-w-[16rem] truncate" title={riskReason(a)}>{riskReason(a)}</td>
                  <td>
                    <span className={`badge ${STATUS_CLS[a.status] ?? 'bg-white/10'}`}>
                      {t(`broker.approval_status.${a.status}`)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap">
                    {canOperate && a.status === 'pending' ? (
                      <div className="flex gap-2">
                        <button
                          className="btn-primary"
                          disabled={busy}
                          onClick={() => approve.mutate(a)}
                        >
                          {t('broker.action.approve')}
                        </button>
                        <button
                          className="btn-ghost"
                          disabled={busy}
                          onClick={() => reject.mutate(a.approval_id)}
                        >
                          {t('broker.action.reject')}
                        </button>
                      </div>
                    ) : a.error ? (
                      <span className="text-danger text-xs">{a.error}</span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
              {approvals.data?.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-4 text-muted text-center">{t('common.empty')}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
