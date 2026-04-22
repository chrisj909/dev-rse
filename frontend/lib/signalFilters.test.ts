import { describe, expect, it } from 'vitest';

import {
  countConfiguredSignalFilters,
  getConfiguredSignalFilterCounts,
  parseSignalFilterStateMap,
  serializeSignalFilterStateMap,
} from './signalFilters';

describe('signal filter state map', () => {
  it('parses include and exclude signals into explicit per-signal states', () => {
    const signalFilters = parseSignalFilterStateMap({
      signals: 'absentee_owner,tax_delinquent',
      excludeSignals: 'corporate_owner',
    });

    expect(signalFilters.absentee_owner).toBe('include');
    expect(signalFilters.tax_delinquent).toBe('include');
    expect(signalFilters.corporate_owner).toBe('exclude');
    expect(signalFilters.eviction).toBe('ignore');
  });

  it('serializes configured signal states back to API params', () => {
    const serialized = serializeSignalFilterStateMap(
      parseSignalFilterStateMap({
        signals: 'probate',
        excludeSignals: 'eviction,code_violation',
      }),
    );

    expect(serialized.signals).toBe('probate');
    expect(serialized.excludeSignals).toBe('eviction,code_violation');
  });

  it('counts included and excluded filters separately', () => {
    const counts = getConfiguredSignalFilterCounts(
      parseSignalFilterStateMap({
        signals: 'absentee_owner,out_of_state_owner',
        excludeSignals: 'corporate_owner',
      }),
    );

    expect(counts).toEqual({ included: 2, excluded: 1 });
    expect(
      countConfiguredSignalFilters(
        parseSignalFilterStateMap({
          signals: 'absentee_owner,out_of_state_owner',
          excludeSignals: 'corporate_owner',
        }),
      ),
    ).toBe(3);
  });
});