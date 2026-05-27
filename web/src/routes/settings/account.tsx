import { useForm } from 'react-hook-form';
import { useMutation } from '@tanstack/react-query';
import { authApi } from '@/api/auth';
import type { ApiError } from '@/api/client';
import { Subheader, Caption } from '@/components/ui/Page';

type Form = { current_password: string; new_password: string };

export default function AccountSettingsPage() {
  const { register, handleSubmit, reset } = useForm<Form>();
  const m = useMutation({
    mutationFn: (v: Form) => authApi.changePassword(v.current_password, v.new_password),
    onSuccess: () => reset(),
  });
  const error = m.error as unknown as ApiError | undefined;

  return (
    <div className="max-w-md">
      <Subheader>账户</Subheader>
      <Caption>修改当前账号的登录密码。</Caption>
      <form className="card space-y-3" onSubmit={handleSubmit((v) => m.mutate(v))}>
        <div>
          <label className="label">当前密码</label>
          <input type="password" className="input" {...register('current_password', { required: true })} />
        </div>
        <div>
          <label className="label">新密码</label>
          <input type="password" className="input" {...register('new_password', { required: true })} />
        </div>
        {error && <div className="text-sm text-danger">{error.status} · {error.detail}</div>}
        {m.isSuccess && <div className="text-sm text-success">已修改</div>}
        <div className="flex justify-end">
          <button className="btn-primary" disabled={m.isPending}>修改密码</button>
        </div>
      </form>
    </div>
  );
}
