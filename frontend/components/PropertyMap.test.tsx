// @vitest-environment jsdom

import { createElement } from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import PropertyMap, { type MapLead } from './PropertyMap';
import { loadLeafletRuntime } from '@/lib/leafletRuntime';

vi.mock('@/lib/leafletRuntime', () => ({
  loadLeafletRuntime: vi.fn(),
}));

interface MarkerStub {
  bindPopup: ReturnType<typeof vi.fn>;
  on: ReturnType<typeof vi.fn>;
  trigger: (eventName: string) => void;
}

interface LeafletMockContext {
  leaflet: Awaited<ReturnType<typeof loadLeafletRuntime>>;
  map: {
    addLayer: ReturnType<typeof vi.fn>;
    getCenter: ReturnType<typeof vi.fn>;
    getZoom: ReturnType<typeof vi.fn>;
    on: ReturnType<typeof vi.fn>;
    remove: ReturnType<typeof vi.fn>;
    removeLayer: ReturnType<typeof vi.fn>;
  };
  markerCluster: {
    addLayer: ReturnType<typeof vi.fn>;
  };
  markers: MarkerStub[];
}

function createLeafletMock(): LeafletMockContext {
  const mapEventHandlers = new Map<string, () => void>();
  const markers: MarkerStub[] = [];
  const markerCluster = {
    addLayer: vi.fn(),
  };
  const map = {
    addLayer: vi.fn(),
    getCenter: vi.fn(() => ({ lat: 33.51, lng: -86.79 })),
    getZoom: vi.fn(() => 11),
    on: vi.fn((eventName: string, handler: () => void) => {
      mapEventHandlers.set(eventName, handler);
    }),
    remove: vi.fn(),
    removeLayer: vi.fn(),
  };
  const leaflet = {
    Icon: {
      Default: {
        prototype: {
          _getIconUrl: vi.fn(),
        },
        mergeOptions: vi.fn(),
      },
    },
    divIcon: vi.fn(() => ({ icon: true })),
    map: vi.fn(() => map),
    marker: vi.fn(() => {
      const markerHandlers = new Map<string, () => void>();
      const marker: MarkerStub = {
        bindPopup: vi.fn(),
        on: vi.fn((eventName: string, handler: () => void) => {
          markerHandlers.set(eventName, handler);
        }),
        trigger: (eventName: string) => {
          markerHandlers.get(eventName)?.();
        },
      };
      markers.push(marker);
      return marker;
    }),
    markerClusterGroup: vi.fn(() => markerCluster),
    tileLayer: vi.fn(() => ({
      addTo: vi.fn(),
    })),
  };

  return {
    leaflet: leaflet as Awaited<ReturnType<typeof loadLeafletRuntime>>,
    map,
    markerCluster,
    markers,
  };
}

const sampleLead: MapLead = {
  property_id: 'prop-1',
  county: 'jefferson',
  parcel_id: 'parcel-1',
  address: '123 Main St',
  city: 'Birmingham',
  owner_name: 'Jane Doe',
  score: 91,
  rank: 'A',
  assessed_value: 250000,
  lat: 33.52,
  lng: -86.8,
};

describe('PropertyMap', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('shows a fallback error panel when Leaflet runtime loading fails', async () => {
    const runtimeError = new Error('Leaflet failed to load');
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.mocked(loadLeafletRuntime).mockRejectedValueOnce(runtimeError);

    render(createElement(PropertyMap, { leads: [] }));

    expect(await screen.findByText('Unable to load the map right now.')).toBeTruthy();
    expect(consoleErrorSpy).toHaveBeenCalledWith('Failed to initialize Leaflet map', runtimeError);

    consoleErrorSpy.mockRestore();
  });

  it('renders markers and forwards map and marker interactions after Leaflet initializes', async () => {
    const { leaflet, map, markerCluster, markers } = createLeafletMock();
    const onPropertyClick = vi.fn();
    const onViewChange = vi.fn();

    vi.mocked(loadLeafletRuntime).mockResolvedValue(leaflet);

    render(createElement(PropertyMap, {
      leads: [sampleLead],
      onPropertyClick,
      onViewChange,
    }));

    await waitFor(() => {
      expect(loadLeafletRuntime).toHaveBeenCalledTimes(2);
    });

    expect(leaflet.map).toHaveBeenCalledTimes(1);
    expect(leaflet.markerClusterGroup).toHaveBeenCalledWith({ chunkedLoading: true });
    expect(leaflet.marker).toHaveBeenCalledWith([sampleLead.lat, sampleLead.lng], { icon: { icon: true } });
    expect(markerCluster.addLayer).toHaveBeenCalledTimes(1);
    expect(map.addLayer).toHaveBeenCalledWith(markerCluster);
    expect(map.on).toHaveBeenCalledWith('moveend zoomend', expect.any(Function));

    markers[0].trigger('click');
    expect(onPropertyClick).toHaveBeenCalledWith(sampleLead);

    const viewChangeHandler = map.on.mock.calls[0][1] as () => void;
    viewChangeHandler();
    expect(onViewChange).toHaveBeenCalledWith([33.51, -86.79], 11);
  });
});