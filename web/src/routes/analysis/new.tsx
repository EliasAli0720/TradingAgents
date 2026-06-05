import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { useMutation } from '@tanstack/react-query';
import { runsApi, type CreateRunInput, type AnalystKey, type AssetType } from '@/api/runs';
import type { ApiError } from '@/api/client';
import { Subheader, Caption } from '@/components/ui/Page';
import { t } from '@/i18n';

const ALL_ANALYSTS: AnalystKey[] = ['market', 'social', 'news', 'fundamentals'];

type Form = {
  ticker: string;
  trade_date: string;
  asset_type: AssetType;
  analysts: Record<AnalystKey, boolean>;
};

export default function AnalysisNewPage() {
  const nav = useNavigate();
  const today = new Date().toISOString().slice(0, 10);

  const { register, handleSubmit, watch, formState: { errors } } = useForm<Form>({
    defaultValues: {
      ticker: '',
      trade_date: today,
      asset_type: 'stock',
      analysts: { market: true, social: true, news: true, fundamentals: true },
    },
  });

  const assetType = watch('asset_type');

  const m = useMutation({
    mutationFn: async (v: Form) => {
      const analysts = ALL_ANALYSTS.filter((k) => v.analysts[k]);
      const input: CreateRunInput = {
        ticker: v.ticker.toUpperCase().trim(),
        trade_date: v.trade_date,
        asset_type: v.asset_type,
        analysts,
      };
      return runsApi.create(input);
    },
    onSuccess: (r) => nav(`/analysis/${r.run_id}`),
  });

  const error = m.error as unknown as ApiError | undefined;

  return (
    <div className="max-w-xl">
      <Subheader>{t('nav.analysis_new')}</Subheader>
      <Caption>{t('analysis.new.caption')}</Caption>

      <form className="card space-y-4" onSubmit={handleSubmit((v) => m.mutate(v))}>
        <div>
          <label className="label">{t('analysis.ticker')}</label>
          <input
            className="input font-mono"
            placeholder="AAPL"
            {...register('ticker', {
              required: t('analysis.ticker.required'),
              pattern: { value: /^[A-Za-z0-9._^-]{1,32}$/, message: t('analysis.ticker.invalid') },
            })}
          />
          {errors.ticker && <div className="text-xs text-danger mt-1">{errors.ticker.message}</div>}
        </div>

        <div>
          <label className="label">{t('analysis.trade_date')}</label>
          <input type="date" className="input" max={today} {...register('trade_date', { required: true })} />
        </div>

        <div>
          <label className="label">{t('analysis.asset_type')}</label>
          <div className="flex gap-6 text-sm">
            <label className="flex items-center gap-2">
              <input type="radio" value="stock" {...register('asset_type')} /> {t('analysis.asset.stock')}
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" value="crypto" {...register('asset_type')} /> {t('analysis.asset.crypto')}
            </label>
          </div>
        </div>

        <div>
          <label className="label">{t('analysis.analysts')}</label>
          <div className="grid grid-cols-2 gap-2 text-sm">
            {ALL_ANALYSTS.map((k) => {
              const disabled = assetType === 'crypto' && k === 'fundamentals';
              return (
                <label key={k} className={`flex items-center gap-2 ${disabled ? 'opacity-40' : ''}`}>
                  <input type="checkbox" disabled={disabled} {...register(`analysts.${k}` as const)} />
                  {k}
                </label>
              );
            })}
          </div>
        </div>

        {error && (
          <div className="text-sm text-danger">
            {error.status} · {error.detail}
            {error.status === 409 && <> · <a href="/settings/model" className="text-brandGold">{t('analysis.configure_model')}</a></>}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={() => nav(-1)}>{t('common.cancel')}</button>
          <button type="submit" className="btn-primary" disabled={m.isPending}>
            {m.isPending ? t('analysis.creating') : t('analysis.run')}
          </button>
        </div>
      </form>
    </div>
  );
}
