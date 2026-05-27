import { useEffect } from 'react';
import clsx from 'clsx';

type Props = {
  open: boolean;
  onClose: () => void;
  side?: 'right' | 'left';
  title?: React.ReactNode;
  width?: number; // px
  children: React.ReactNode;
};

export default function Drawer({ open, onClose, side = 'right', title, width = 360, children }: Props) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose(); }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  return (
    <div
      className={clsx(
        'fixed inset-0 z-40 transition',
        open ? 'pointer-events-auto' : 'pointer-events-none',
      )}
      aria-hidden={!open}
    >
      {/* backdrop */}
      <div
        className={clsx(
          'absolute inset-0 bg-black/50 transition-opacity',
          open ? 'opacity-100' : 'opacity-0',
        )}
        onClick={onClose}
      />

      {/* panel */}
      <aside
        className={clsx(
          'absolute top-0 h-full bg-panel border-border shadow-2xl transition-transform duration-200 ease-out flex flex-col',
          side === 'right'
            ? clsx('right-0 border-l', open ? 'translate-x-0' : 'translate-x-full')
            : clsx('left-0 border-r',  open ? 'translate-x-0' : '-translate-x-full'),
        )}
        style={{ width }}
      >
        <header className="h-12 shrink-0 px-4 flex items-center justify-between border-b border-border">
          <div className="font-semibold">{title}</div>
          <button className="btn-ghost px-2 py-1" onClick={onClose} aria-label="关闭">✕</button>
        </header>
        <div className="flex-1 overflow-y-auto p-4 text-sm">
          {children}
        </div>
      </aside>
    </div>
  );
}
