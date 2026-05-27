import { http } from './client';
import type { Role } from './auth';
import type { RunStatus, RunSummary } from './runs';

export type AdminUser = {
  user_id: string;
  username: string;
  role: Role;
  is_active: boolean;
};

export const adminApi = {
  async users(): Promise<AdminUser[]> {
    const { data } = await http.get<AdminUser[]>('/admin/users');
    return data;
  },
  async patchUser(
    userId: string,
    patch: { role?: Role; is_active?: boolean },
  ): Promise<AdminUser> {
    const { data } = await http.patch<AdminUser>(`/admin/users/${userId}`, patch);
    return data;
  },
  async revokeSessions(userId: string): Promise<void> {
    await http.post(`/admin/users/${userId}/sessions:revoke-all`);
  },
  async runs(params?: { user_id?: string; status_filter?: RunStatus }): Promise<RunSummary[]> {
    const { data } = await http.get<RunSummary[]>('/admin/runs', { params });
    return data;
  },
};
