import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { adminApi, type AdminUser } from '@/api/admin';
import type { Role } from '@/api/auth';
import { Subheader, Caption } from '@/components/ui/Page';

export default function AdminUsersPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['admin', 'users'], queryFn: adminApi.users });

  const patch = useMutation({
    mutationFn: (v: { id: string; patch: Partial<Pick<AdminUser, 'role' | 'is_active'>> }) =>
      adminApi.patchUser(v.id, v.patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  });

  const revoke = useMutation({ mutationFn: (id: string) => adminApi.revokeSessions(id) });

  return (
    <div>
      <Subheader>用户管理</Subheader>
      <Caption>修改角色 / 启停状态，或撤销该用户的全部会话。</Caption>

      {q.isLoading ? (
        <div className="text-muted">加载中…</div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="df">
            <thead>
              <tr>
                <th>用户名</th>
                <th>角色</th>
                <th>启用</th>
                <th>会话</th>
              </tr>
            </thead>
            <tbody>
              {q.data?.map((u) => (
                <tr key={u.user_id}>
                  <td className="font-mono">{u.username}</td>
                  <td>
                    <select
                      className="input w-32"
                      value={u.role}
                      onChange={(e) => patch.mutate({ id: u.user_id, patch: { role: e.target.value as Role } })}
                    >
                      <option value="admin">admin</option>
                      <option value="operator">operator</option>
                      <option value="viewer">viewer</option>
                    </select>
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      checked={u.is_active}
                      onChange={(e) => patch.mutate({ id: u.user_id, patch: { is_active: e.target.checked } })}
                    />
                  </td>
                  <td>
                    <button
                      className="btn-ghost text-xs"
                      onClick={() => { if (confirm(`撤销 ${u.username} 的所有会话？`)) revoke.mutate(u.user_id); }}
                    >
                      撤销所有
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
