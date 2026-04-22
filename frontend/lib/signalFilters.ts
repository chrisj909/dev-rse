export const SIGNAL_FILTERS = [
  { value: 'absentee_owner', label: 'Absentee Owner', description: 'Owner mailing address differs from the property address.' },
  { value: 'long_term_owner', label: 'Long-Term Owner', description: 'Owner has held the property for 10 or more years.' },
  { value: 'out_of_state_owner', label: 'Out-of-State Owner', description: 'Owner mailing address is outside Alabama.' },
  { value: 'corporate_owner', label: 'Corporate Owner', description: 'Owner name looks like an LLC, Inc., or other entity.' },
  { value: 'tax_delinquent', label: 'Tax Delinquent', description: 'Property appears on the tax delinquency source list.' },
  { value: 'pre_foreclosure', label: 'Pre-Foreclosure', description: 'Property is flagged in the foreclosure pipeline.' },
  { value: 'probate', label: 'Probate', description: 'Probate activity suggests an inherited property scenario.' },
  { value: 'eviction', label: 'Eviction', description: 'Property is linked to eviction-related activity.' },
  { value: 'code_violation', label: 'Code Violation', description: 'Property matches a Birmingham 311 code violation record.' },
] as const;

export type SignalFilterValue = (typeof SIGNAL_FILTERS)[number]['value'];
export type SignalMatchMode = 'all' | 'any';
export type SignalFilterState = 'ignore' | 'include' | 'exclude';
export type SignalFilterStateMap = Record<SignalFilterValue, SignalFilterState>;

const SIGNAL_FILTER_MAP = new Map<string, (typeof SIGNAL_FILTERS)[number]>(
  SIGNAL_FILTERS.map(signal => [signal.value, signal]),
);

export function parseSignalFilterValue(value?: string | null): SignalFilterValue[] {
  if (!value) {
    return [];
  }

  const parsed = value
    .split(',')
    .map(part => part.trim())
    .filter((part): part is SignalFilterValue => SIGNAL_FILTER_MAP.has(part));

  return Array.from(new Set(parsed));
}

export function createEmptySignalFilterStateMap(): SignalFilterStateMap {
  return Object.fromEntries(
    SIGNAL_FILTERS.map(signal => [signal.value, 'ignore']),
  ) as SignalFilterStateMap;
}

export function parseSignalFilterStateMap({
  signals,
  excludeSignals,
}: {
  signals?: string | null;
  excludeSignals?: string | null;
}): SignalFilterStateMap {
  const nextState = createEmptySignalFilterStateMap();

  for (const signal of parseSignalFilterValue(signals)) {
    nextState[signal] = 'include';
  }

  for (const signal of parseSignalFilterValue(excludeSignals)) {
    nextState[signal] = 'exclude';
  }

  return nextState;
}

export function serializeSignalFilterValue(signals: string[]): string | null {
  const normalized = Array.from(new Set(signals.filter(signal => SIGNAL_FILTER_MAP.has(signal))));
  return normalized.length > 0 ? normalized.join(',') : null;
}

export function serializeSignalFilterStateMap(signalFilters: SignalFilterStateMap): {
  signals: string | null;
  excludeSignals: string | null;
} {
  const includedSignals = SIGNAL_FILTERS
    .filter(signal => signalFilters[signal.value] === 'include')
    .map(signal => signal.value);
  const excludedSignals = SIGNAL_FILTERS
    .filter(signal => signalFilters[signal.value] === 'exclude')
    .map(signal => signal.value);

  return {
    signals: serializeSignalFilterValue(includedSignals),
    excludeSignals: serializeSignalFilterValue(excludedSignals),
  };
}

export function countConfiguredSignalFilters(signalFilters: SignalFilterStateMap): number {
  return Object.values(signalFilters).filter(state => state !== 'ignore').length;
}

export function getConfiguredSignalFilterCounts(signalFilters: SignalFilterStateMap): {
  included: number;
  excluded: number;
} {
  return Object.values(signalFilters).reduce(
    (counts, state) => {
      if (state === 'include') {
        counts.included += 1;
      } else if (state === 'exclude') {
        counts.excluded += 1;
      }
      return counts;
    },
    { included: 0, excluded: 0 },
  );
}

export function normalizeSignalMatchMode(value?: string | null): SignalMatchMode {
  return value === 'any' ? 'any' : 'all';
}

export function getSignalLabel(value: string): string {
  return SIGNAL_FILTER_MAP.get(value)?.label ?? value.replaceAll('_', ' ');
}

export function getSignalDescription(value: string): string | null {
  return SIGNAL_FILTER_MAP.get(value)?.description ?? null;
}