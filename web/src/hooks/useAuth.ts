import { useQuery, useQueryClient } from '@tanstack/react-query';
import { authApi, type Me } from '@/api/auth';

export function useAuth() {
  const qc = useQueryClient();
  const q = useQuery<Me | null>({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      try {
        return await authApi.me();
      } catch {
        return null;
      }
    },
    staleTime: 60_000,
  });

  return {
    user: q.data ?? null,
    isLoading: q.isLoading,
    isAdmin: q.data?.role === 'admin',
    canOperate: q.data?.role === 'admin' || q.data?.role === 'operator',
    refetch: q.refetch,
    invalidate: () => qc.invalidateQueries({ queryKey: ['auth', 'me'] }),
  };
}
