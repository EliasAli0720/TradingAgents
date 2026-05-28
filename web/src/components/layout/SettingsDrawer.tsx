import { NavLink, useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import { useAuth } from '@/hooks/useAuth';
import { authApi, type Language } from '@/api/auth';
import { t, getLang, setLang } from '@/i18n';
import Drawer from '@/components/ui/Drawer';

type Item = { to: string; label: string; adminOnly?: boolean };

const GROUPS: { title: string; items: Item[] }[] = [
  {
    title: 'group.settings',
    items: [
      { to: '/settings/model', label: 'nav.model' },
      { to: '/settings/translation', label: 'nav.translation' },
      { to: '/settings/account', label: 'nav.account' },
    ],
  },
  {
    title: 'group.admin',
    items: [
      { to: '/admin/users', label: 'nav.admin_users', adminOnly: true },
      { to: '/admin/runs', label: 'nav.admin_runs', adminOnly: true },
    ],
  },
];

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
      {/* Language */}
      <div className="flex items-center justify-between gap-3 mb-3 flex-nowrap whitespace-nowrap">
        <span className="text-muted shrink-0">{t('app.sidebar.language')}</span>
        <select
          className="input w-32 py-1 shrink-0"
          value={lang}
          onChange={(e) => handleLanguageChange(e.target.value as Language)}
        >
          <option value="zh">中文</option>
          <option value="en">English</option>
        </select>
      </div>

      <div className="st-divider" />

      {/* Account block */}
      {user ? (
        <div className="mb-3">
          <div className="text-sm">{t('app.sidebar.signed_in', { name: user.username })}</div>
          <div className="text-xs text-muted mb-2">{t('settings.role', { role: user.role })}</div>
          <button className="btn-ghost btn-block" onClick={handleLogout}>
            {t('app.sidebar.logout')}
          </button>
        </div>
      ) : (
        <div className="text-muted text-sm mb-3">{t('settings.not_signed_in')}</div>
      )}

      <div className="st-divider" />

      {/* Settings + admin nav */}
      <div className="nav-radio">
        {GROUPS.map((g) => {
          const visible = g.items.filter((i) => !i.adminOnly || isAdmin);
          if (visible.length === 0) return null;
          return (
            <div key={g.title}>
              <div className="group-label">{t(g.title)}</div>
              {visible.map((i) => (
                <NavLink
                  key={i.to}
                  to={i.to}
                  end
                  onClick={onClose}
                  className={({ isActive }) => clsx(isActive && 'active')}
                >
                  <span className="dot" />
                  <span>{t(i.label)}</span>
                </NavLink>
              ))}
            </div>
          );
        })}
      </div>
    </Drawer>
  );
}
