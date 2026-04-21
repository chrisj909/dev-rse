'use client';
import { useEffect, useRef, useState } from 'react';
import type { Map as LeafletMap, Layer } from 'leaflet';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import 'leaflet.markercluster/dist/MarkerCluster.Default.css';
import { loadLeafletRuntime } from '@/lib/leafletRuntime';

export interface MapLead {
  property_id: string;
  county: string;
  parcel_id: string;
  address: string | null;
  city: string | null;
  owner_name: string | null;
  score: number;
  rank: string;
  assessed_value: number | null;
  lat: number;
  lng: number;
}

const RANK_COLORS: Record<string, string> = {
  A: '#16a34a',
  B: '#ca8a04',
  C: '#6b7280',
};

interface Props {
  leads: MapLead[];
  onPropertyClick?: (lead: MapLead) => void;
  center?: [number, number];
  zoom?: number;
  onViewChange?: (center: [number, number], zoom: number) => void;
}

export default function PropertyMap({ leads, onPropertyClick, center, zoom, onViewChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const clusterRef = useRef<Layer | null>(null);
  const [isMapReady, setIsMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    let isActive = true;

    async function initializeMap() {
      try {
        const L = await loadLeafletRuntime();
        if (!isActive || !containerRef.current) {
          return;
        }

        // Fix default icon paths broken by webpack
        delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
        L.Icon.Default.mergeOptions({
          iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
          iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
          shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
        });

        const defaultCenter: [number, number] = center ?? [33.4, -86.8];
        const defaultZoom = zoom ?? 10;

        const map = L.map(containerRef.current, {
          center: defaultCenter,
          zoom: defaultZoom,
          zoomControl: true,
        });

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
          maxZoom: 19,
        }).addTo(map);

        mapRef.current = map;
        setMapError(null);
        setIsMapReady(true);

        if (onViewChange) {
          map.on('moveend zoomend', () => {
            const c = map.getCenter();
            onViewChange([c.lat, c.lng], map.getZoom());
          });
        }
      } catch (error) {
        if (!isActive) {
          return;
        }
        console.error('Failed to initialize Leaflet map', error);
        setMapError('Unable to load the map right now.');
      }
    }

    void initializeMap();

    return () => {
      isActive = false;

      if (clusterRef.current && mapRef.current) {
        mapRef.current.removeLayer(clusterRef.current);
        clusterRef.current = null;
      }

      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }

      setIsMapReady(false);
    };
  }, []);

  // Rebuild cluster group whenever leads change
  useEffect(() => {
    if (!isMapReady || !mapRef.current) return;

    let isActive = true;

    async function rebuildClusters() {
      try {
        const L = await loadLeafletRuntime();
        if (!isActive || !mapRef.current) {
          return;
        }

        const map = mapRef.current;

        // Remove previous cluster group
        if (clusterRef.current) {
          map.removeLayer(clusterRef.current);
          clusterRef.current = null;
        }

        const cluster = L.markerClusterGroup({ chunkedLoading: true });

        leads.forEach(lead => {
          const color = RANK_COLORS[lead.rank] ?? '#6b7280';
          const icon = L.divIcon({
            className: '',
            html: `<div style="width:12px;height:12px;border-radius:50%;background:${color};border:2px solid rgba(255,255,255,0.8);box-shadow:0 1px 3px rgba(0,0,0,0.4)"></div>`,
            iconSize: [12, 12],
            iconAnchor: [6, 6],
          });

          const marker = L.marker([lead.lat, lead.lng], { icon });

          const value = lead.assessed_value != null
            ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(lead.assessed_value)
            : '—';

          marker.bindPopup(`
            <div style="min-width:180px;font-family:sans-serif;font-size:13px">
              <div style="font-weight:600;margin-bottom:4px">${lead.address || 'Address unavailable'}</div>
              <div style="color:#6b7280;font-size:11px;margin-bottom:6px">${[lead.city, lead.county ? lead.county.charAt(0).toUpperCase() + lead.county.slice(1) + ' County' : ''].filter(Boolean).join(' · ')}</div>
              ${lead.owner_name ? `<div style="font-size:11px;margin-bottom:4px">${lead.owner_name}</div>` : ''}
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                <span style="background:${color};color:${lead.rank === 'B' ? '#000' : '#fff'};padding:1px 8px;border-radius:4px;font-size:11px;font-weight:700">${lead.rank}</span>
                <span style="font-weight:600">Score: ${lead.score}</span>
                <span style="color:#6b7280">${value}</span>
              </div>
              <a href="/property?parcel_id=${encodeURIComponent(lead.parcel_id)}&county=${encodeURIComponent(lead.county)}" style="color:#3b82f6;font-size:12px">View detail →</a>
            </div>
          `);

          if (onPropertyClick) {
            marker.on('click', () => onPropertyClick(lead));
          }

          cluster.addLayer(marker);
        });

        map.addLayer(cluster);
        clusterRef.current = cluster;
        setMapError(null);
      } catch (error) {
        if (!isActive) {
          return;
        }
        console.error('Failed to render Leaflet markers', error);
        setMapError('Unable to render map markers right now.');
      }
    }

    void rebuildClusters();

    return () => {
      isActive = false;
    };
  }, [isMapReady, leads, onPropertyClick]);

  if (mapError) {
    return (
      <div className="flex min-h-[500px] w-full items-center justify-center rounded-xl border border-red-800 bg-red-950/40 px-4 text-center text-sm text-red-100">
        {mapError}
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="w-full h-full rounded-xl overflow-hidden"
      style={{ minHeight: '500px' }}
    />
  );
}
