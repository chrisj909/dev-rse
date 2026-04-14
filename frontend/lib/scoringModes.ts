export const SCORING_MODES = [
  { value: 'broad', label: 'Broad' },
  { value: 'owner_occupant', label: 'Owner-Occupant Seller' },
  { value: 'investor', label: 'Investor Acquisition' },
] as const;

export type ScoringMode = (typeof SCORING_MODES)[number]['value'];

export const DEFAULT_SCORING_MODE: ScoringMode = 'broad';

export function normalizeScoringMode(value?: string | null): ScoringMode {
  return (SCORING_MODES.find(mode => mode.value === value)?.value ?? DEFAULT_SCORING_MODE) as ScoringMode;
}

export function getScoringModeLabel(value?: string | null): string {
  return SCORING_MODES.find(mode => mode.value === normalizeScoringMode(value))?.label ?? 'Broad';
}