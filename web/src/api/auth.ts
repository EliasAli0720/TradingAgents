import { http } from './client';

export type Role = 'admin' | 'operator' | 'viewer';

export type Me = {
  user_id: string;
  username: string;
  role: Role;
};

export const authApi = {
  async login(username: string, password: string): Promise<Me> {
    const { data } = await http.post<Me>('/auth/login', { username, password });
    return data;
  },
  async register(username: string, password: string): Promise<Me> {
    const { data } = await http.post<Me>('/auth/register', { username, password });
    return data;
  },
  async me(): Promise<Me> {
    const { data } = await http.get<Me>('/auth/me');
    return data;
  },
  async logout(): Promise<void> {
    await http.post('/auth/logout');
  },
  async changePassword(current_password: string, new_password: string): Promise<void> {
    await http.post('/auth/change-password', { current_password, new_password });
  },
};
