import { useAuth } from '@/hooks/useAuth';
import type { Role } from '@/api/auth';
import { t } from '@/i18n';

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
        {t('settings.no_permission')}
      </div>
    );
  }
  return <>{children}</>;
}
