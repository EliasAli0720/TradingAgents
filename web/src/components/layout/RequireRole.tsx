import { useAuth } from '@/hooks/useAuth';
import type { Role } from '@/api/auth';

export default function RequireRole({
  roles,
  children,
}: {
  roles: Role[];
  children: React.ReactNode;
}) {
  const { user } = useAuth();
  if (!user || !roles.includes(user.role)) {
    return (
      <div className="card text-muted">
        当前账号没有访问该页面的权限。
      </div>
    );
  }
  return <>{children}</>;
}
