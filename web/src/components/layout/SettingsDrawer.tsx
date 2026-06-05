import { NavLink, useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import { useAuth } from '@/hooks/useAuth';
import { authApi, type Language } from '@/api/auth';
import { t, getLang, setLang } from '@/i18n';
import Drawer from '@/components/ui/Drawer';

const ADMIN_GROUP = {
  title: 'group.admin',
  items: [
    { to: '/admin/users', label: 'nav.admin_users' },
    { to: '/admin/runs', label: 'nav.admin_runs' },
  ],
} as const;

const SETTINGS_GROUP = {
  title: 'group.settings',
  items: [
    { to: '/settings/model', label: 'nav.model' },
    { to: '/settings/translation', label: 'nav.translation' },
    { to: '/settings/account', label: 'nav.account' },
  ],
} as const;

function NavGroup({
  group,
  onNavigate,
}: {
  group: { title: string; items: readonly { to: string; label: string }[] };
  onNavigate: () => void;
}) {
  return (
    <div className="nav-radio">
      <div className="group-label">{t(group.title)}</div>
      {group.items.map((i) => (
        <NavLink
          key={i.to}
          to={i.to}
          end
          onClick={onNavigate}
          className={({ isActive }) => clsx(isActive && 'active')}
        >
          <span className="dot" />
          <span>{t(i.label)}</span>
        </NavLink>
      ))}
    </div>
  );
}

export default function SettingsDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user, isAdmin, invalidate } = useAuth();
  const nav = useNavigate();
  const lang = getLang();

  async function handleLogout() {
    try { await authApi.logout(); } catch {}
    await invalidate();
    onClose();
    nav('/login', { replace: true });
  }

  async function handleLanguageChange(next: Language) {
    // Persist to DB first (source of truth); setLang reloads to re-render.
    try { await authApi.setPreferences(next); } catch {}
    setLang(next);
  }

  return (
    <Drawer open={open} onClose={onClose} title={t('settings.title')} width={360}>
      {/* Account */}
      <section className="card mb-4 min-w-0 space-y-4">
        {user ? (
          <>
            <div className="space-y-2">
              <div className="text-sm font-medium leading-relaxed">
                {t('app.sidebar.signed_in', { name: user.username })}
              </div>
              <div className="text-xs text-muted leading-relaxed">
                {t('settings.role', { role: user.role })}
              </div>
            </div>
            <button className="btn-ghost btn-block" onClick={handleLogout}>
              {t('app.sidebar.logout')}
            </button>
          </>
        ) : (
          <div className="text-sm text-muted leading-relaxed py-1">{t('settings.not_signed_in')}</div>
        )}
      </section>

      <div className="st-divider" />

      {/* Admin */}
      {isAdmin && (
        <>
          <NavGroup group={ADMIN_GROUP} onNavigate={onClose} />
          <div className="st-divider" />
        </>
      )}

      {/* Language */}
      <section className="card mb-4 min-w-0 space-y-3">
        <div>
          <label className="label mb-0">{t('app.sidebar.language')}</label>
          <p className="st-caption mt-1">{t('settings.language_hint')}</p>
        </div>
        <select
          className="input"
          value={lang}
          onChange={(e) => handleLanguageChange(e.target.value as Language)}
        >
          <option value="zh">中文</option>
          <option value="en">English</option>
        </select>
      </section>

      <div className="st-divider" />

      {/* Settings */}
      <NavGroup group={SETTINGS_GROUP} onNavigate={onClose} />
    </Drawer>
  );
}
