'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import { getClientApiBaseUrl } from '@/lib/api';
import { SCORING_MODES, type ScoringMode } from '@/lib/scoringModes';

export interface ScoreModeHealthStats {
  properties: number;
  signals: number;
  scores: Record<string, number>;
  score_schema?: {
    property_mode_unique_constraint?: boolean;
  };
}

interface UseScoreModeHealthOptions {
  refreshIntervalMs?: number;
}

export function useScoreModeHealth({ refreshIntervalMs = 30000 }: UseScoreModeHealthOptions = {}) {
  const [stats, setStats] = useState<ScoreModeHealthStats | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async ({ silent = false }: { silent?: boolean } = {}) => {
    if (!silent) {
      setLoading(true);
    }

    try {
      const response = await fetch(`${getClientApiBaseUrl()}/api/health/stats`);
      if (!response.ok) {
        return;
      }
      const payload = await response.json() as ScoreModeHealthStats;
      setStats(payload);
    } catch {
      // Non-critical; the rest of the app can still run without the health overlay.
    } finally {
      if (!silent) {
        setLoading(false);
      } else {
        setLoading(current => (current ? false : current));
      }
    }
  }, []);

  useEffect(() => {
    void refresh();

    if (refreshIntervalMs <= 0) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refresh({ silent: true });
    }, refreshIntervalMs);

    return () => window.clearInterval(intervalId);
  }, [refresh, refreshIntervalMs]);

  const modeCounts = useMemo(
    () => Object.fromEntries(
      SCORING_MODES.map(mode => [mode.value, stats?.scores?.[mode.value] ?? 0]),
    ) as Record<ScoringMode, number>,
    [stats],
  );

  const unavailableModes = useMemo(
    () => SCORING_MODES.filter(mode => modeCounts[mode.value] === 0),
    [modeCounts],
  );

  const isModeAvailable = useCallback(
    (mode: string) => SCORING_MODES.some(option => option.value === mode && modeCounts[option.value] > 0),
    [modeCounts],
  );

  return {
    stats,
    loading,
    modeCounts,
    unavailableModes,
    hasIncompleteCoverage: unavailableModes.length > 0,
    isModeAvailable,
    refresh,
  };
}