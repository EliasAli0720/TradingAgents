import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import SettingsDrawer from './SettingsDrawer';
import { PageTitle } from '@/components/ui/Page';
import { t } from '@/i18n';

export default function AppLayout() {
  const [settingsOpen, setSettingsOpen] = useState(false);

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
        aria-label="打开设置"
      >
        <span className="text-base leading-none">⚙</span>
        <span>设置</span>
      </button>

      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
