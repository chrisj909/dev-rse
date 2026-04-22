'use client';
import { Suspense, useState, useEffect, useCallback, useMemo, useRef } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { usePropertyLists } from '@/hooks/usePropertyLists';
import { useSavedSearches } from '@/hooks/useSavedSearches';
import SavedSearchesModal from '@/components/SavedSearchesModal';
import ScoreCoverageNotice from '@/components/ScoreCoverageNotice';
import type { MapLead } from '@/components/PropertyMap';
import { getClientApiBaseUrl } from '@/lib/api';
import { fetchMapLeads } from '@/lib/mapLeads';
import { DEFAULT_SCORING_MODE, SCORING_MODES, normalizeScoringMode } from '@/lib/scoringModes';
import { useScoreModeHealth } from '@/hooks/useScoreModeHealth';

const PropertyMap = dynamic(() => import('@/components/PropertyMap'), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center bg-gray-800 rounded-xl" style={{ minHeight: '500px' }}>
      <span className="text-gray-400 text-sm">Loading map…</span>
    </div>
  ),
});

function RankBadge({ rank }: { rank?: string }) {
  if (!rank) return null;
  const colors: Record<string, string> = {
    A: 'bg-green-600 text-white',
    B: 'bg-yellow-500 text-black',
    C: 'bg-gray-500 text-white',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-bold ${colors[rank] ?? 'bg-gray-600 text-white'}`}>
      {rank}
    </span>
  );
}

type ScoringMode = 'broad' | 'owner_occupant' | 'investor';

export default function MapPage() {
  return (
    <Suspense fallback={<div className="flex flex-col h-full p-4 sm:p-6 gap-4" style={{ minHeight: 'calc(100vh - 4rem)' }}><div className="rounded-xl border border-gray-700 bg-gray-800/95 px-4 py-6 text-sm text-gray-300">Loading map view…</div></div>}>
      <MapPageContent />
    </Suspense>
  );
}

function MapPageContent() {
  const searchParams = useSearchParams();
  const [leads, setLeads] = useState<MapLead[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadProgress, setLoadProgress] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [scoringMode, setScoringMode] = useState<ScoringMode>('broad');
  const [rank, setRank] = useState('');
  const [county, setCounty] = useState('');
  const [search, setSearch] = useState('');
  const [mapCenter, setMapCenter] = useState<[number, number]>([33.4, -86.8]);
  const [mapZoom, setMapZoom] = useState(10);
  const [selectedLead, setSelectedLead] = useState<MapLead | null>(null);

  // Save view
  const { user } = useAuth();
  const { save: saveSearch } = useSavedSearches();
  const { lists, addToList } = usePropertyLists();
  const [savingView, setSavingView] = useState(false);
  const [viewName, setViewName] = useState('');
  const [showSaveInput, setShowSaveInput] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [addListId, setAddListId] = useState('');
  const fetchGeneration = useRef(0);
  const { loading: scoreModeHealthLoading, modeCounts, hasIncompleteCoverage, isModeAvailable } = useScoreModeHealth();
  const hasUnavailableSelectedMode = scoringMode !== DEFAULT_SCORING_MODE && !isModeAvailable(scoringMode);
  const listViewHref = useMemo(() => {
    const params = new URLSearchParams();
    if (scoringMode !== DEFAULT_SCORING_MODE) {
      params.set('scoring_mode', scoringMode);
    }
    if (rank) {
      params.set('rank', rank);
    }
    if (county) {
      params.set('county', county);
    }
    if (search.trim()) {
      params.set('search', search.trim());
    }

    const query = params.toString();
    return query ? `/leads?${query}` : '/leads';
  }, [county, rank, scoringMode, search]);

  useEffect(() => {
    const nextScoringMode = normalizeScoringMode(searchParams.get('scoring_mode')) as ScoringMode;
    const nextRank = ['A', 'B', 'C'].includes(searchParams.get('rank') ?? '') ? searchParams.get('rank') ?? '' : '';
    const nextCounty = ['shelby', 'jefferson'].includes(searchParams.get('county') ?? '') ? searchParams.get('county') ?? '' : '';
    const nextSearch = searchParams.get('search') ?? '';
    const nextLat = Number(searchParams.get('map_lat'));
    const nextLng = Number(searchParams.get('map_lng'));
    const nextZoom = Number(searchParams.get('map_zoom'));

    setScoringMode(nextScoringMode);
    setRank(nextRank);
    setCounty(nextCounty);
    setSearch(nextSearch);
    setMapCenter(
      Number.isFinite(nextLat) && Number.isFinite(nextLng)
        ? [nextLat, nextLng]
        : [33.4, -86.8],
    );
    setMapZoom(Number.isFinite(nextZoom) && nextZoom > 0 ? nextZoom : 10);
    setSelectedLead(null);
  }, [searchParams]);

  const fetchLeads = useCallback(async () => {
    const generation = fetchGeneration.current + 1;
    fetchGeneration.current = generation;
    setLoading(true);
    setLoadProgress('Loading map leads...');
    setFetchError(null);

    try {
      const result = await fetchMapLeads<MapLead>({
        baseUrl: getClientApiBaseUrl(),
        scoringMode,
        rank,
        county,
        search,
        onPage: (progress) => {
          if (fetchGeneration.current !== generation) {
            return;
          }
          setLoadProgress(`Loaded ${progress.fetched.toLocaleString()} / ${progress.total.toLocaleString()} records...`);
        },
      });
      if (fetchGeneration.current !== generation) {
        return;
      }
      setLeads(result.leads);
      setTotal(result.total);
    } catch (err: unknown) {
      if (fetchGeneration.current !== generation) {
        return;
      }
      setLeads([]);
      setTotal(0);
      setFetchError(err instanceof Error ? err.message : 'Unable to load map leads.');
    } finally {
      if (fetchGeneration.current === generation) {
        setLoading(false);
        setLoadProgress(null);
      }
    }
  }, [scoringMode, rank, county, search]);

  useEffect(() => { fetchLeads(); }, [fetchLeads]);

  async function handleSaveView() {
    if (!viewName.trim()) return;
    setSavingView(true);
    await saveSearch(viewName.trim(), {
      scoring_mode: scoringMode,
      rank,
      county,
      search,
      map_lat: String(mapCenter[0]),
      map_lng: String(mapCenter[1]),
      map_zoom: String(mapZoom),
    });
    setViewName('');
    setShowSaveInput(false);
    setSavingView(false);
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 2000);
  }

  async function handleAddToList() {
    if (!selectedLead || !addListId) return;
    await addToList(addListId, selectedLead.county, selectedLead.parcel_id);
    setAddListId('');
  }

  const mappedCount = leads.length;
  const unmappedCount = Math.max(0, total - mappedCount);

  return (
    <div className="flex flex-col h-full p-4 sm:p-6 gap-4" style={{ minHeight: 'calc(100vh - 4rem)' }}>
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Map View</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            {loading ? 'Loading…' : `${mappedCount} mapped · ${total} total`}
            {unmappedCount > 0 && <span className="text-gray-500"> · {unmappedCount} without coords</span>}
          </p>
          {loading && loadProgress && (
            <p className="text-slate-400 text-xs mt-1">{loadProgress}</p>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Link
            href={listViewHref}
            className="text-xs text-gray-400 hover:text-white border border-gray-700 rounded-lg px-3 py-1.5 transition-colors"
          >
            ☰ List View
          </Link>
          <SavedSearchesModal trigger="Saved Views" targetPath="/map" />
          {user && (
            showSaveInput ? (
              <div className="flex items-center gap-2">
                <input
                  autoFocus
                  type="text"
                  value={viewName}
                  onChange={e => setViewName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSaveView()}
                  placeholder="View name…"
                  className="rounded-lg border border-gray-600 bg-gray-800 px-2.5 py-1.5 text-xs text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                />
                <button
                  onClick={handleSaveView}
                  disabled={!viewName.trim() || savingView}
                  className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
                >
                  {savingView ? '…' : 'Save'}
                </button>
                <button onClick={() => setShowSaveInput(false)} className="text-gray-400 hover:text-white text-xs">Cancel</button>
              </div>
            ) : saveSuccess ? (
              <span className="text-green-400 text-xs font-medium">✓ View saved</span>
            ) : (
              <button
                onClick={() => setShowSaveInput(true)}
                className="text-xs text-gray-300 hover:text-white border border-gray-700 rounded-lg px-3 py-1.5 transition-colors"
              >
                Save View
              </button>
            )
          )}
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-2 flex-wrap rounded-xl border border-gray-700 bg-gray-800/95 px-4 py-3">
        <select
          value={scoringMode}
          onChange={e => setScoringMode(e.target.value as ScoringMode)}
          className="rounded-lg border border-gray-600 bg-gray-900/80 px-3 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none"
        >
          {SCORING_MODES.map(mode => {
            const unavailable = !scoreModeHealthLoading && mode.value !== DEFAULT_SCORING_MODE && modeCounts[mode.value] === 0;
            return (
              <option key={mode.value} value={mode.value} disabled={unavailable}>
                {mode.label}{unavailable ? ' (unavailable)' : ''}
              </option>
            );
          })}
        </select>
        <select
          value={county}
          onChange={e => setCounty(e.target.value)}
          className="rounded-lg border border-gray-600 bg-gray-900/80 px-3 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none"
        >
          <option value="">All counties</option>
          <option value="shelby">Shelby</option>
          <option value="jefferson">Jefferson</option>
        </select>
        <div className="flex gap-1">
          {['', 'A', 'B', 'C'].map(r => (
            <button
              key={r}
              onClick={() => setRank(r)}
              className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${rank === r ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}`}
            >
              {r || 'All'}
            </button>
          ))}
        </div>
        <input
          type="text"
          placeholder="Search address / owner…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && fetchLeads()}
          className="rounded-lg border border-gray-600 bg-gray-900/80 px-3 py-1.5 text-xs text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none flex-1 min-w-[160px]"
        />
        <button
          onClick={fetchLeads}
          disabled={loading}
          className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-60"
        >
          {loading ? '…' : 'Apply'}
        </button>
      </div>

      {hasIncompleteCoverage && (
        <ScoreCoverageNotice
          modeCounts={modeCounts}
          selectedMode={scoringMode}
          title="Map views are safest on the broad lens right now."
          description="The map can still drive broad lead review, but signal-based search in Leads is the better workflow until the other score modes finish repopulating."
          onSwitchToBroad={hasUnavailableSelectedMode ? () => setScoringMode(DEFAULT_SCORING_MODE) : undefined}
        />
      )}

      {fetchError && (
        <div className="rounded-xl border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-200">
          {fetchError}
        </div>
      )}

      {/* Map + sidebar */}
      <div className="flex gap-4 flex-1" style={{ minHeight: '500px' }}>
        {/* Map */}
        <div className="flex-1 relative">
          <PropertyMap
            leads={leads}
            center={mapCenter}
            zoom={mapZoom}
            onViewChange={(c, z) => { setMapCenter(c); setMapZoom(z); }}
            onPropertyClick={lead => setSelectedLead(lead)}
          />
          {/* Legend */}
          <div className="absolute bottom-4 left-4 z-[1000] bg-gray-900/90 rounded-lg px-3 py-2 text-xs text-gray-300 space-y-1 border border-gray-700">
            <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-green-600 inline-block" /> Rank A</div>
            <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-yellow-500 inline-block" /> Rank B</div>
            <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-gray-500 inline-block" /> Rank C</div>
          </div>
        </div>

        {/* Property detail panel */}
        {selectedLead && (
          <div className="w-72 flex-shrink-0 bg-gray-800 border border-gray-700 rounded-xl p-4 space-y-3 overflow-y-auto">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-white text-sm font-semibold leading-tight">{selectedLead.address || 'Address unavailable'}</p>
                <p className="text-gray-400 text-xs mt-0.5">
                  {[selectedLead.city, selectedLead.county ? selectedLead.county.charAt(0).toUpperCase() + selectedLead.county.slice(1) + ' County' : ''].filter(Boolean).join(' · ')}
                </p>
              </div>
              <button onClick={() => setSelectedLead(null)} className="text-gray-500 hover:text-white text-lg leading-none flex-shrink-0">×</button>
            </div>

            {selectedLead.owner_name && (
              <p className="text-gray-300 text-xs">{selectedLead.owner_name}</p>
            )}

            <div className="flex items-center gap-3">
              <RankBadge rank={selectedLead.rank} />
              <span className="text-white font-mono font-bold">{selectedLead.score}</span>
              {selectedLead.assessed_value != null && (
                <span className="text-gray-400 text-xs ml-auto">
                  {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(selectedLead.assessed_value)}
                </span>
              )}
            </div>

            <div className="flex gap-2 flex-wrap">
              <Link
                href={`/property?parcel_id=${encodeURIComponent(selectedLead.parcel_id)}&county=${encodeURIComponent(selectedLead.county)}&scoring_mode=${scoringMode}`}
                className="flex-1 text-center text-xs text-blue-400 hover:text-blue-300 border border-blue-700/50 rounded-lg px-3 py-1.5 transition-colors"
              >
                View Detail
              </Link>
              <a
                href={`https://maps.google.com/?q=${encodeURIComponent([selectedLead.address, selectedLead.city, 'AL'].filter(Boolean).join(', '))}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 text-center text-xs text-gray-300 hover:text-white border border-gray-700 rounded-lg px-3 py-1.5 transition-colors"
              >
                Maps ↗
              </a>
            </div>

            {user && lists.length > 0 && (
              <div className="flex gap-2">
                <select
                  value={addListId}
                  onChange={e => setAddListId(e.target.value)}
                  className="flex-1 rounded-lg border border-gray-600 bg-gray-900/80 px-2 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none"
                >
                  <option value="">Add to list…</option>
                  {lists.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
                <button
                  onClick={handleAddToList}
                  disabled={!addListId}
                  className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
                >
                  Add
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
