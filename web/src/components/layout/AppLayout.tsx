import { useEffect, useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import SettingsDrawer from './SettingsDrawer';
import { PageTitle } from '@/components/ui/Page';
import { t, syncLangFromServer } from '@/i18n';
import { useAuth } from '@/hooks/useAuth';
import { useSnapshotPush } from '@/hooks/useSnapshotPush';

export default function AppLayout() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { user } = useAuth();
  useSnapshotPush(); // push equity snapshots to the server while connected

  // Reconcile UI language with the DB-stored preference on mount / login.
  useEffect(() => {
    if (user?.language) syncLangFromServer(user.language);
  }, [user?.language]);

  return (
    <div className="h-full flex relative">
      <Sidebar />
      <main className="flex-1 overflow-auto p-8 bg-bg">
        <PageTitle>{t('app.title')}</PageTitle>
        <Outlet />
      </main>

      {/* Floating settings button, top-right */}
      <button
        className="fixed top-4 right-4 z-30 btn-ghost flex items-center gap-2 shadow-lg backdrop-blur"
        onClick={() => setSettingsOpen(true)}
        aria-label={t('settings.open')}
      >
        <span className="text-base leading-none">⚙</span>
        <span>{t('settings.title')}</span>
      </button>

      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
