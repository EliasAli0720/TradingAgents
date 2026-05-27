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
    <div className="h-full flex items-center justify-center p-6">
      <div className="card w-full max-w-sm">
        <h1 className="st-title mb-1">{t('app.title')}</h1>
        <div className="st-caption mb-5">
          {mode === 'login' ? t('auth.subtitle.login') : t('auth.subtitle.register')}
        </div>

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
            <button className="text-[#ff4b4b]" onClick={() => setMode('register')}>{t('auth.go_register')}</button>
          ) : (
            <button className="text-[#ff4b4b]" onClick={() => setMode('login')}>{t('auth.go_login')}</button>
          )}
        </div>
      </div>
    </div>
  );
}
