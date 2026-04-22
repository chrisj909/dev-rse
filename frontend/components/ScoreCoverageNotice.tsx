'use client';

import { DEFAULT_SCORING_MODE, getScoringModeLabel, type ScoringMode } from '@/lib/scoringModes';

interface ScoreCoverageNoticeProps {
  modeCounts: Record<ScoringMode, number>;
  selectedMode?: string;
  title: string;
  description: string;
  onSwitchToBroad?: () => void;
}

const MODE_LABELS: Record<ScoringMode, string> = {
  broad: 'Broad',
  owner_occupant: 'Owner-Occupant',
  investor: 'Investor',
};

function getCountBadgeClass(mode: ScoringMode, count: number): string {
  if (mode === 'broad') {
    return 'border-sky-500/40 bg-sky-500/10 text-sky-100';
  }

  if (count > 0) {
    return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100';
  }

  return 'border-slate-600/80 bg-slate-800/90 text-slate-300';
}

export default function ScoreCoverageNotice({
  modeCounts,
  selectedMode = DEFAULT_SCORING_MODE,
  title,
  description,
  onSwitchToBroad,
}: ScoreCoverageNoticeProps) {
  const selectedModeUnavailable = selectedMode !== DEFAULT_SCORING_MODE && modeCounts[selectedMode as ScoringMode] === 0;

  return (
    <div className="rounded-2xl border border-slate-700 bg-gradient-to-r from-slate-950 via-slate-900 to-slate-950 px-4 py-4 shadow-[0_18px_45px_rgba(15,23,42,0.24)] sm:px-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-sky-300">Score Health</p>
          <p className="mt-2 text-sm font-semibold text-white">{title}</p>
          <p className="mt-1 text-sm text-slate-300">{description}</p>
        </div>

        {selectedModeUnavailable && onSwitchToBroad && (
          <button
            type="button"
            onClick={onSwitchToBroad}
            className="rounded-full border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs font-medium text-sky-100 transition-colors hover:bg-sky-500/20"
          >
            Switch Back to {getScoringModeLabel(DEFAULT_SCORING_MODE)}
          </button>
        )}
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {(Object.keys(MODE_LABELS) as ScoringMode[]).map(mode => (
          <div
            key={mode}
            className={`rounded-full border px-3 py-1.5 text-xs font-medium ${getCountBadgeClass(mode, modeCounts[mode])}`}
          >
            <span className="text-[11px] uppercase tracking-wide opacity-75">{MODE_LABELS[mode]}</span>
            <span className="ml-2 font-semibold text-sm">{modeCounts[mode].toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}