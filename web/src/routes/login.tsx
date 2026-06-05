import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { authApi } from '@/api/auth';
import { useAuth } from '@/hooks/useAuth';
import type { ApiError } from '@/api/client';
import { t } from '@/i18n';

type Form = { username: string; password: string };

export default function LoginPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const { invalidate } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const next = params.get('next') ?? '/';
  const { register, handleSubmit, formState: { errors } } = useForm<Form>();

  const m = useMutation({
    mutationFn: async (v: Form) => {
      if (mode === 'register') {
        await authApi.register(v.username, v.password);
        return authApi.login(v.username, v.password);
      }
      return authApi.login(v.username, v.password);
    },
    onSuccess: async () => {
      await invalidate();
      nav(next, { replace: true });
    },
  });

  const error = m.error as unknown as ApiError | undefined;

  return (
    <div className="h-full overflow-y-auto overflow-x-hidden flex items-center justify-center bg-[radial-gradient(circle_at_top,rgba(221,170,83,0.18),transparent_36%),linear-gradient(135deg,#0C3D2F_0%,#051A10_70%)] p-4 sm:p-6">
      <div className="card w-full max-w-sm my-auto">
        <div className="mb-5 grid justify-items-center gap-3 rounded-lg border border-brandGold/30 bg-[linear-gradient(145deg,#F7F4EA_0%,#EEF0E7_58%,#C6CDBF_100%)] px-5 py-5 text-center shadow-lg shadow-black/15">
          <img
            src="/brand/icon.png"
            alt=""
            className="h-20 w-20 rounded-2xl object-cover shadow-md shadow-black/15 ring-1 ring-brandGold/45"
            aria-hidden="true"
          />
          <div className="w-full min-w-0 max-w-[15rem]">
            <img
              src="/brand/logo.png"
              alt={t('app.sidebar.title')}
              className="mx-auto h-9 w-full max-w-full object-contain"
            />
            <div className="mt-2 text-xs leading-snug text-[#3B563F] break-words">{t('app.sidebar.product_tagline')}</div>
          </div>
        </div>
        {mode === 'register' && (
          <div className="st-caption mb-5">{t('auth.subtitle.register')}</div>
        )}

        <form className="space-y-3" onSubmit={handleSubmit((v) => m.mutate(v))}>
          <div>
            <label className="label">{t('auth.username')}</label>
            <input
              className="input"
              autoFocus
              {...register('username', { required: t('auth.username') })}
            />
            {errors.username && <div className="text-xs text-danger mt-1">{errors.username.message}</div>}
          </div>
          <div>
            <label className="label">{t('auth.password')}</label>
            <input
              className="input"
              type="password"
              {...register('password', { required: t('auth.password') })}
            />
            {errors.password && <div className="text-xs text-danger mt-1">{errors.password.message}</div>}
          </div>

          {error && (
            <div className="text-sm text-danger">{error.status} · {error.detail}</div>
          )}

          <button className="btn-primary btn-block" type="submit" disabled={m.isPending}>
            {m.isPending ? t('common.loading') : mode === 'login' ? t('auth.login') : t('auth.register')}
          </button>
        </form>

        <div className="st-divider" />
        <div className="text-sm text-muted text-center">
          {mode === 'login' ? (
            <button className="text-brandGold" onClick={() => setMode('register')}>{t('auth.go_register')}</button>
          ) : (
            <button className="text-brandGold" onClick={() => setMode('login')}>{t('auth.go_login')}</button>
          )}
        </div>
      </div>
    </div>
  );
}
