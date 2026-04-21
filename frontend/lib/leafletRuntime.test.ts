import { beforeEach, describe, expect, it, vi } from 'vitest';

const { leafletModule, markerClusterImportSpy } = vi.hoisted(() => ({
  leafletModule: {
    Icon: {
      Default: {
        prototype: {},
        mergeOptions: vi.fn(),
      },
    },
    divIcon: vi.fn(),
    map: vi.fn(),
    marker: vi.fn(),
    markerClusterGroup: vi.fn(),
    tileLayer: vi.fn(),
  },
  markerClusterImportSpy: vi.fn(),
}));

vi.mock('leaflet', () => leafletModule);
vi.mock('leaflet.markercluster', () => {
  markerClusterImportSpy(globalThis.L);
  return {};
});

import { loadLeafletRuntime, resetLeafletRuntimeForTest } from './leafletRuntime';

describe('loadLeafletRuntime', () => {
  beforeEach(() => {
    resetLeafletRuntimeForTest();
    markerClusterImportSpy.mockClear();
  });

  it('publishes Leaflet globally before loading markercluster', async () => {
    const loadedLeaflet = await loadLeafletRuntime();

    expect(loadedLeaflet.map).toBe(leafletModule.map);
    expect(globalThis.L?.map).toBe(leafletModule.map);
    expect(markerClusterImportSpy).toHaveBeenCalledTimes(1);
    expect(markerClusterImportSpy.mock.calls[0][0]?.map).toBe(leafletModule.map);
  });
});