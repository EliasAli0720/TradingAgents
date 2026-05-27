import clsx from 'clsx';
import type { RunStatus } from '@/api/runs';
import type { RunEvent } from '@/hooks/useRunEvents';
import { t } from '@/i18n';

type Stage = {
  key: string;
  labelKey: string;
  percent: number;
};

const STAGES: Stage[] = [
  { key: 'queued', labelKey: 'run.stage.queued', percent: 5 },
  { key: 'preparing', labelKey: 'run.stage.preparing', percent: 15 },
  { key: 'analyzing', labelKey: 'run.stage.analyzing', percent: 35 },
  { key: 'saving', labelKey: 'run.stage.saving', percent: 85 },
  { key: 'completed', labelKey: 'run.stage.completed', percent: 100 },
];

const DEFAULT_MESSAGES: Record<string, string> = {
  queued: 'run.message.queued',
  preparing: 'run.message.preparing',
  analyzing: 'run.message.analyzing',
  saving: 'run.message.saving',
  completed: 'run.message.completed',
  failed: 'run.message.failed',
  cancelled: 'run.message.cancelled',
};

export default function RunProgress({
  status,
  events,
  currentStep,
}: {
  status: RunStatus;
  events: RunEvent[];
  currentStep?: string | null;
}) {
  const latestProgress = [...events]
    .reverse()
    .find((event) => event.event === 'run_progress' && isProgressPayload(event.data));
  const payload = latestProgress && isProgressPayload(latestProgress.data) ? latestProgress.data : null;
  const phase = resolvePhase(status, payload?.phase);
  const percent = resolvePercent(status, phase, payload?.percent);
  const message = resolveMessage(status, payload?.message, currentStep, phase);
  const activeIndex = STAGES.findIndex((stage) => stage.key === phase);

  return (
    <div className="card mb-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-sm font-semibold">{titleForStatus(status)}</div>
          <div className="text-sm text-muted mt-1">{message}</div>
        </div>
        <div className="text-sm font-semibold text-muted">{percent}%</div>
      </div>

      <div className="mt-4 h-2 rounded-full bg-bg border border-border overflow-hidden">
        <div
          className={clsx(
            'h-full transition-all duration-500',
            status === 'failed' ? 'bg-danger' : status === 'cancelled' ? 'bg-muted' : 'bg-[#ff4b4b]',
          )}
          style={{ width: `${percent}%` }}
        />
      </div>

      <div className="mt-4 grid grid-cols-2 md:grid-cols-5 gap-2">
        {STAGES.map((stage, index) => {
          const done = status === 'succeeded' || (activeIndex >= 0 && index <= activeIndex);
          const active = stage.key === phase && status !== 'succeeded';
          return (
            <div
              key={stage.key}
              className={clsx(
                'rounded-md border px-3 py-2 min-h-16',
                done ? 'border-[#ff4b4b]/70 bg-[#ff4b4b]/10' : 'border-border bg-bg/30',
                active && 'ring-1 ring-[#ff4b4b]',
              )}
            >
              <div className={clsx('text-xs uppercase text-muted', done && 'text-text/80')}>
                {index + 1}
              </div>
              <div className="text-sm font-medium mt-1">{t(stage.labelKey)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function isProgressPayload(value: unknown): value is {
  phase?: string;
  percent?: number;
  message?: string;
} {
  return typeof value === 'object' && value !== null;
}

function resolvePhase(status: RunStatus, phase: string | undefined): string {
  if (status === 'succeeded') return 'completed';
  if (phase && STAGES.some((stage) => stage.key === phase)) return phase;
  if (status === 'failed' || status === 'cancelled') return 'analyzing';
  if (status === 'running') return 'analyzing';
  return 'queued';
}

function resolvePercent(status: RunStatus, phase: string, percent: number | undefined): number {
  if (status === 'succeeded') return 100;
  if (status === 'failed' || status === 'cancelled') return percent ?? STAGES.find((stage) => stage.key === phase)?.percent ?? 0;
  if (typeof percent === 'number') return Math.max(0, Math.min(99, Math.round(percent)));
  return STAGES.find((stage) => stage.key === phase)?.percent ?? 0;
}

function resolveMessage(
  status: RunStatus,
  message: string | undefined,
  currentStep: string | null | undefined,
  phase: string,
): string {
  if (status === 'failed') return t(DEFAULT_MESSAGES.failed);
  if (status === 'cancelled') return t(DEFAULT_MESSAGES.cancelled);
  if (message) return message;
  if (currentStep) return currentStep;
  return t(DEFAULT_MESSAGES[phase] ?? DEFAULT_MESSAGES.analyzing);
}

function titleForStatus(status: RunStatus): string {
  if (status === 'queued') return t('run.title.queued');
  if (status === 'running') return t('run.title.running');
  if (status === 'succeeded') return t('run.title.succeeded');
  if (status === 'failed') return t('run.title.failed');
  return t('run.title.cancelled');
}
