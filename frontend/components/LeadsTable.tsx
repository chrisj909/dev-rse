'use client';
import { type FormEvent, useState, useTransition } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';

import { DEFAULT_SCORING_MODE, SCORING_MODES, getScoringModeLabel } from '../lib/scoringModes';
import { exportLeadResultsToCsv } from '../lib/leadExport';
import {
  SIGNAL_FILTERS,
  countConfiguredSignalFilters,
  createEmptySignalFilterStateMap,
  getConfiguredSignalFilterCounts,
  getSignalLabel,
  normalizeSignalMatchMode,
  parseSignalFilterStateMap,
  serializeSignalFilterStateMap,
  type SignalFilterState,
  type SignalFilterStateMap,
  type SignalFilterValue,
  type SignalMatchMode,
} from '../lib/signalFilters';
import SaveSearchButton from './SaveSearchButton';
import ScoreCoverageNotice from './ScoreCoverageNotice';
import SavedSearchesModal from './SavedSearchesModal';
import { usePropertyLists } from '@/hooks/usePropertyLists';
import { useAuth } from '@/contexts/AuthContext';
import { getClientApiBaseUrl } from '@/lib/api';
import { useScoreModeHealth } from '@/hooks/useScoreModeHealth';

interface Lead {
  county: string;
  parcel_id: string;
  address: string | null;
  city: string | null;
  state: string;
  zip: string | null;
  owner_name: string | null;
  mailing_address: string | null;
  assessed_value: number | null;
  score: number;
  rank: string;
  scoring_mode?: string;
  signal_count: number;
  signals: string[];
  last_updated: string;
}

interface FilterState {
  search?: string;
  county?: string;
  city?: string;
  owner?: string;
  parcel_id?: string;
  min_score?: string;
  max_score?: string;
  min_value?: string;
  max_value?: string;
  rank?: string;
  scoring_mode?: string;
  signals?: string;
  exclude_signals?: string;
  signal_match?: string;
  sort_by?: string;
  sort_dir?: string;
  page?: string;
  page_size?: string;
}

type SortKey = 'score' | 'address' | 'city' | 'county' | 'assessed_value' | 'last_updated' | 'rank' | 'owner_name';
type SortDir = 'asc' | 'desc';

function formatCounty(county: string) {
  if (!county) return 'County unavailable';
  return `${county.charAt(0).toUpperCase()}${county.slice(1)} County`;
}

function RankBadge({ rank }: { rank: string }) {
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

function SortIcon({ col, sortKey, sortDir }: { col: SortKey; sortKey: SortKey; sortDir: SortDir }) {
  if (sortKey !== col) return <span className="text-gray-600 ml-1">↕</span>;
  return <span className="text-blue-400 ml-1">{sortDir === 'asc' ? '↑' : '↓'}</span>;
}

export default function LeadsTable({
  leads,
  total,
  pageSize,
  offset,
  initialFilters,
}: {
  leads: Lead[];
  total: number;
  pageSize: number;
  offset: number;
  initialFilters: FilterState;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [search, setSearch] = useState(initialFilters.search ?? '');
  const [countyFilter, setCountyFilter] = useState(initialFilters.county ?? 'All');
  const [cityFilter, setCityFilter] = useState(initialFilters.city ?? '');
  const [ownerFilter, setOwnerFilter] = useState(initialFilters.owner ?? '');
  const [parcelFilter, setParcelFilter] = useState(initialFilters.parcel_id ?? '');
  const [minScore, setMinScore] = useState(initialFilters.min_score ?? '');
  const [maxScore, setMaxScore] = useState(initialFilters.max_score ?? '');
  const [minValue, setMinValue] = useState(initialFilters.min_value ?? '');
  const [maxValue, setMaxValue] = useState(initialFilters.max_value ?? '');
  const [rankFilter, setRankFilter] = useState<string>(initialFilters.rank ?? 'All');
  const [scoringMode, setScoringMode] = useState(initialFilters.scoring_mode ?? DEFAULT_SCORING_MODE);
  const [signalFilters, setSignalFilters] = useState<SignalFilterStateMap>(() => parseSignalFilterStateMap({
    signals: initialFilters.signals,
    excludeSignals: initialFilters.exclude_signals,
  }));
  const [signalMatch, setSignalMatch] = useState<SignalMatchMode>(normalizeSignalMatchMode(initialFilters.signal_match));
  const [sortKey, setSortKey] = useState<SortKey>((initialFilters.sort_by as SortKey) ?? 'score');
  const [sortDir, setSortDir] = useState<SortDir>((initialFilters.sort_dir as SortDir) ?? 'desc');
  const [searchOpen, setSearchOpen] = useState(false);
  const [exportingResults, setExportingResults] = useState(false);
  const [exportStatus, setExportStatus] = useState<string | null>(null);
  const { modeCounts, hasIncompleteCoverage, isModeAvailable } = useScoreModeHealth();

  // Multi-select
  const { user } = useAuth();
  const { lists, addManyToList, createList } = usePropertyLists();
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [bulkListId, setBulkListId] = useState('');
  const [bulkAdding, setBulkAdding] = useState(false);
  const [bulkSuccess, setBulkSuccess] = useState(false);
  const [bulkNewName, setBulkNewName] = useState('');
  const [bulkShowNew, setBulkShowNew] = useState(false);

  function selKey(lead: Lead) { return `${lead.county}:${lead.parcel_id}`; }

  function toggleSelect(e: React.MouseEvent | React.ChangeEvent, lead: Lead) {
    e.stopPropagation();
    const k = selKey(lead);
    setSelectedKeys(prev => {
      const next = new Set(prev);
      next.has(k) ? next.delete(k) : next.add(k);
      return next;
    });
  }

  function toggleSelectAll(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.checked) {
      setSelectedKeys(new Set(leads.map(selKey)));
    } else {
      setSelectedKeys(new Set());
    }
  }

  async function handleBulkAdd(listId: string) {
    setBulkAdding(true);
    const items = leads
      .filter(l => selectedKeys.has(selKey(l)))
      .map(l => ({ county: l.county, parcel_id: l.parcel_id }));
    await addManyToList(listId, items);
    setBulkAdding(false);
    setBulkSuccess(true);
    setSelectedKeys(new Set());
    setTimeout(() => setBulkSuccess(false), 2000);
  }

  async function handleBulkCreateAndAdd() {
    if (!bulkNewName.trim()) return;
    setBulkAdding(true);
    const list = await createList(bulkNewName.trim());
    if (list) await handleBulkAdd(list.id);
    setBulkNewName('');
    setBulkShowNew(false);
    setBulkAdding(false);
  }

  const page = Math.floor(offset / pageSize) + 1;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const { signals: selectedSignalParam, excludeSignals: excludedSignalParam } = serializeSignalFilterStateMap(signalFilters);
  const { included: includedSignalCount, excluded: excludedSignalCount } = getConfiguredSignalFilterCounts(signalFilters);
  const hasUnavailableSelectedMode = scoringMode !== DEFAULT_SCORING_MODE && !isModeAvailable(scoringMode);

  const activeFilterCount = [
    search,
    countyFilter !== 'All' ? countyFilter : '',
    cityFilter,
    ownerFilter,
    parcelFilter,
    minScore,
    maxScore,
    minValue,
    maxValue,
    rankFilter !== 'All' ? rankFilter : '',
    scoringMode !== DEFAULT_SCORING_MODE ? scoringMode : '',
    countConfiguredSignalFilters(signalFilters) > 0 ? String(countConfiguredSignalFilters(signalFilters)) : '',
  ].filter(Boolean).length;

  const currentPageCount = leads.length;

  function buildQuery(overrides: Record<string, string | null>) {
    const params = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(overrides)) {
      if (value == null || value === '' || value === 'All') {
        params.delete(key);
      } else {
        params.set(key, value);
      }
    }
    return params.toString();
  }

  function navigate(overrides: Record<string, string | null>) {
    const query = buildQuery(overrides);
    startTransition(() => {
      router.push(query ? `${pathname}?${query}` : pathname);
    });
  }

  function getPersistedFilters(): Record<string, string> {
    return Object.fromEntries(
      Object.entries({
        search,
        county: countyFilter !== 'All' ? countyFilter : '',
        city: cityFilter,
        owner: ownerFilter,
        parcel_id: parcelFilter,
        min_score: minScore,
        max_score: maxScore,
        min_value: minValue,
        max_value: maxValue,
        rank: rankFilter !== 'All' ? rankFilter : '',
        scoring_mode: scoringMode,
        signals: selectedSignalParam ?? '',
        exclude_signals: excludedSignalParam ?? '',
        signal_match: selectedSignalParam ? signalMatch : '',
        sort_by: sortKey,
        sort_dir: sortDir,
      }).filter(([, value]) => value && value !== 'All')
    ) as Record<string, string>;
  }

  function setSignalFilterState(signal: SignalFilterValue, nextState: SignalFilterState) {
    setSignalFilters(prev => ({
      ...prev,
      [signal]: nextState,
    }));
  }

  function toggleSort(key: SortKey) {
    let nextDir: SortDir = key === 'rank' ? 'asc' : 'desc';
    if (sortKey === key) {
      nextDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      setSortKey(key);
    }
    setSortDir(nextDir);
    navigate({ sort_by: key, sort_dir: nextDir, page: '1' });
  }

  function navigateToLead(lead: Lead) {
    const params = new URLSearchParams({ parcel_id: lead.parcel_id, county: lead.county });
    if (scoringMode !== DEFAULT_SCORING_MODE) params.set('scoring_mode', scoringMode);
    router.push(`/property?${params.toString()}`);
  }

  function formatCurrency(value: number | null) {
    if (value == null) return '—';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
    }).format(value);
  }

  function clearFilters() {
    setSearch('');
    setCountyFilter('All');
    setCityFilter('');
    setOwnerFilter('');
    setParcelFilter('');
    setMinScore('');
    setMaxScore('');
    setMinValue('');
    setMaxValue('');
    setRankFilter('All');
    setScoringMode(DEFAULT_SCORING_MODE);
    setSignalFilters(createEmptySignalFilterStateMap());
    setSignalMatch('all');
    setSortKey('score');
    setSortDir('desc');
    navigate({
      search: null,
      county: null,
      city: null,
      owner: null,
      parcel_id: null,
      min_score: null,
      max_score: null,
      min_value: null,
      max_value: null,
      rank: null,
      scoring_mode: null,
      signals: null,
      exclude_signals: null,
      signal_match: null,
      sort_by: null,
      sort_dir: null,
      page: null,
      page_size: null,
    });
  }

  function applyFilters() {
    navigate({
      search,
      county: countyFilter,
      city: cityFilter,
      owner: ownerFilter,
      parcel_id: parcelFilter,
      min_score: minScore,
      max_score: maxScore,
      min_value: minValue,
      max_value: maxValue,
      rank: rankFilter,
      scoring_mode: scoringMode,
      signals: selectedSignalParam,
      exclude_signals: excludedSignalParam,
      signal_match: selectedSignalParam ? signalMatch : null,
      sort_by: sortKey,
      sort_dir: sortDir,
      page: '1',
      page_size: String(pageSize),
    });
  }

  async function exportCurrentSearch() {
    setExportingResults(true);
    setExportStatus('Preparing export…');

    try {
      const filters = getPersistedFilters();
      const filenameParts = [
        countyFilter !== 'All' ? countyFilter : 'all_counties',
        countConfiguredSignalFilters(signalFilters) > 0 ? `${countConfiguredSignalFilters(signalFilters)}_signal_rules` : 'all_leads',
        new Date().toISOString().slice(0, 10),
      ];

      const { total: exportedTotal } = await exportLeadResultsToCsv(
        `${filenameParts.join('_')}.csv`,
        {
          baseUrl: getClientApiBaseUrl(),
          filters,
          onPage: (progress) => {
            setExportStatus(`Exporting ${progress.fetched.toLocaleString()} / ${progress.total.toLocaleString()} leads…`);
          },
        },
      );
      setExportStatus(`Exported ${exportedTotal.toLocaleString()} leads.`);
      setTimeout(() => setExportStatus(null), 2500);
    } catch (error) {
      setExportStatus(error instanceof Error ? error.message : 'Unable to export current results.');
    } finally {
      setExportingResults(false);
    }
  }

  function handleFilterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    applyFilters();
  }

  return (
    <div className="space-y-4">
      <form
        onSubmit={handleFilterSubmit}
        className="rounded-2xl border border-gray-700 bg-gray-800/95 p-5 shadow-[0_18px_45px_rgba(15,23,42,0.28)]"
      >
        <div className="flex items-center gap-3 flex-wrap">
          <button
            type="button"
            onClick={() => setSearchOpen(o => !o)}
            className="flex items-center gap-1.5 rounded-full border border-gray-600 bg-gray-700/80 px-3 py-1 text-xs font-medium text-gray-300 transition-colors hover:border-gray-500 hover:bg-gray-700"
          >
            <span>{searchOpen ? '▲' : '▼'}</span>
            <span>Search & Filter</span>
          </button>
          <div className="rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 text-xs font-medium text-blue-200">
            {total} matches
          </div>
          {activeFilterCount > 0 && (
            <div className="rounded-full border border-gray-600 bg-gray-700/80 px-3 py-1 text-xs font-medium text-gray-300">
              {activeFilterCount} active filters
            </div>
          )}
          <div className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-200">
            {getScoringModeLabel(scoringMode)}
          </div>
          {searchOpen && (
            <>
              <button
                type="submit"
                disabled={isPending}
                className="rounded-full bg-blue-600 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-60"
              >
                {isPending ? 'Updating...' : 'Apply'}
              </button>
              <button
                type="button"
                onClick={clearFilters}
                className="rounded-full border border-gray-600 px-3 py-1 text-xs font-medium text-gray-300 transition-colors hover:border-gray-500 hover:bg-gray-700"
              >
                Reset
              </button>
            </>
          )}
          <div className="ml-auto flex items-center gap-2">
            <SavedSearchesModal />
            <button
              type="button"
              onClick={exportCurrentSearch}
              disabled={exportingResults || total === 0}
              className="rounded-full border border-gray-600 px-3 py-1 text-xs font-medium text-gray-300 transition-colors hover:border-emerald-500 hover:text-white disabled:cursor-not-allowed disabled:border-gray-700 disabled:text-gray-600"
            >
              {exportingResults ? 'Exporting…' : 'Export Results'}
            </button>
            <SaveSearchButton
              filters={getPersistedFilters()}
              activeFilterCount={activeFilterCount}
            />
          </div>
        </div>

        {exportStatus && (
          <p className={`mt-3 text-xs ${exportStatus.startsWith('Unable') ? 'text-red-300' : 'text-emerald-300'}`}>
            {exportStatus}
          </p>
        )}

        {hasIncompleteCoverage && (
          <div className="mt-4">
            <ScoreCoverageNotice
              modeCounts={modeCounts}
              selectedMode={scoringMode}
              title="Signal search is the stable workflow while rescoring runs."
              description="These filters work regardless of score coverage, so you can keep building targeted lists even while owner-occupant and investor rows are still catching up."
              onSwitchToBroad={hasUnavailableSelectedMode ? () => {
                setScoringMode(DEFAULT_SCORING_MODE);
                navigate({ scoring_mode: null, page: '1' });
              } : undefined}
            />
          </div>
        )}

        {/* Bulk action bar */}
        {selectedKeys.size > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-blue-700/50 bg-blue-900/20 px-4 py-2.5">
            <span className="text-blue-200 text-sm font-medium">{selectedKeys.size} selected</span>
            {!user ? (
              <Link href="/auth" className="text-xs text-blue-400 underline">Sign in to add to list</Link>
            ) : bulkSuccess ? (
              <span className="text-green-400 text-xs font-medium">✓ Added to list</span>
            ) : bulkShowNew ? (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  autoFocus
                  value={bulkNewName}
                  onChange={e => setBulkNewName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleBulkCreateAndAdd()}
                  placeholder="New list name…"
                  className="rounded-lg border border-gray-600 bg-gray-900/80 px-2.5 py-1 text-xs text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                />
                <button
                  onClick={handleBulkCreateAndAdd}
                  disabled={!bulkNewName.trim() || bulkAdding}
                  className="rounded-lg bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
                >
                  {bulkAdding ? '…' : 'Create & Add'}
                </button>
                <button onClick={() => setBulkShowNew(false)} className="text-gray-400 hover:text-white text-xs">Cancel</button>
              </div>
            ) : (
              <div className="flex items-center gap-2 flex-wrap">
                {lists.length > 0 && (
                  <select
                    value={bulkListId}
                    onChange={e => setBulkListId(e.target.value)}
                    className="rounded-lg border border-gray-600 bg-gray-900/80 px-2.5 py-1 text-xs text-white focus:border-blue-500 focus:outline-none"
                  >
                    <option value="">Choose list…</option>
                    {lists.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                  </select>
                )}
                {bulkListId && (
                  <button
                    onClick={() => handleBulkAdd(bulkListId)}
                    disabled={bulkAdding}
                    className="rounded-lg bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
                  >
                    {bulkAdding ? 'Adding…' : 'Add to List'}
                  </button>
                )}
                <button
                  onClick={() => setBulkShowNew(true)}
                  className="rounded-lg border border-gray-600 px-3 py-1 text-xs text-gray-300 hover:text-white transition-colors"
                >
                  + New list
                </button>
              </div>
            )}
            <button
              onClick={() => setSelectedKeys(new Set())}
              className="ml-auto text-gray-500 hover:text-white text-xs"
            >
              Clear
            </button>
          </div>
        )}

        {searchOpen && (<>
        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">Scoring Lens</span>
            <select
              value={scoringMode}
              onChange={e => setScoringMode(e.target.value)}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white focus:border-blue-500 focus:outline-none"
            >
              {SCORING_MODES.map(mode => (
                <option key={mode.value} value={mode.value}>{mode.label}</option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">County</span>
            <select
              value={countyFilter}
              onChange={e => setCountyFilter(e.target.value)}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white focus:border-blue-500 focus:outline-none"
            >
              <option value="All">All counties</option>
              <option value="shelby">Shelby County</option>
              <option value="jefferson">Jefferson County</option>
            </select>
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">Global Search</span>
            <input
              type="text"
              placeholder="Address, owner, or parcel"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">City</span>
            <input
              type="text"
              placeholder="Leeds, Birmingham..."
              value={cityFilter}
              onChange={e => setCityFilter(e.target.value)}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">Owner</span>
            <input
              type="text"
              placeholder="Owner name"
              value={ownerFilter}
              onChange={e => setOwnerFilter(e.target.value)}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">Parcel ID</span>
            <input
              type="text"
              placeholder="01 6 23 ..."
              value={parcelFilter}
              onChange={e => setParcelFilter(e.target.value)}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </label>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">Min Score</span>
            <input
              type="number"
              placeholder="0"
              value={minScore}
              onChange={e => setMinScore(e.target.value)}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">Max Score</span>
            <input
              type="number"
              placeholder="100"
              value={maxScore}
              onChange={e => setMaxScore(e.target.value)}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">Min Value</span>
            <input
              type="number"
              placeholder="50000"
              value={minValue}
              onChange={e => setMinValue(e.target.value)}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">Max Value</span>
            <input
              type="number"
              placeholder="500000"
              value={maxValue}
              onChange={e => setMaxValue(e.target.value)}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <div>
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">Rank</span>
            <div className="flex gap-2">
              {['All', 'A', 'B', 'C'].map(r => (
                <button
                  key={r}
                  type="button"
                  onClick={() => { setRankFilter(r); navigate({ rank: r, page: '1' }); }}
                  className={`rounded-xl px-4 py-2.5 text-sm font-medium transition-colors ${
                    rankFilter === r
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-4 rounded-2xl border border-gray-700/70 bg-gray-900/40 p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-gray-400">Signal Filters</p>
              <p className="mt-1 text-xs text-gray-500">Configure each signal individually. Require it, exclude it, or leave it open.</p>
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <span>{includedSignalCount} required · {excludedSignalCount} excluded</span>
              {includedSignalCount > 1 && (
                <div className="flex items-center gap-1 rounded-full border border-gray-700 bg-gray-800/80 p-1">
                  {(['all', 'any'] as SignalMatchMode[]).map(mode => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setSignalMatch(mode)}
                      className={`rounded-full px-3 py-1 font-medium transition-colors ${signalMatch === mode ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-700'}`}
                    >
                      Match {mode}
                    </button>
                  ))}
                </div>
              )}
              {countConfiguredSignalFilters(signalFilters) > 0 && (
                <button
                  type="button"
                  onClick={() => setSignalFilters(createEmptySignalFilterStateMap())}
                  className="rounded-full border border-gray-700 px-3 py-1 font-medium text-gray-300 hover:border-gray-500 hover:text-white"
                >
                  Clear Signals
                </button>
              )}
            </div>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {SIGNAL_FILTERS.map(signal => {
              const configuredState = signalFilters[signal.value];
              return (
                <div
                  key={signal.value}
                  className={`rounded-2xl border p-4 transition-colors ${configuredState === 'ignore' ? 'border-gray-700 bg-gray-800/50' : configuredState === 'include' ? 'border-emerald-500/60 bg-emerald-500/10' : 'border-rose-500/60 bg-rose-500/10'}`}
                >
                  <div>
                    <p className="text-sm font-medium text-white">{signal.label}</p>
                    <p className="mt-1 text-xs text-gray-400">{signal.description}</p>
                  </div>
                  <div className="mt-3 flex items-center gap-1 rounded-full border border-gray-700 bg-gray-900/70 p-1 text-xs">
                    {([
                      { value: 'ignore', label: 'Any' },
                      { value: 'include', label: 'Has' },
                      { value: 'exclude', label: 'Skip' },
                    ] as Array<{ value: SignalFilterState; label: string }>).map(option => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => setSignalFilterState(signal.value, option.value)}
                        className={`flex-1 rounded-full px-3 py-1.5 font-medium transition-colors ${configuredState === option.value ? option.value === 'include' ? 'bg-emerald-500/20 text-emerald-100' : option.value === 'exclude' ? 'bg-rose-500/20 text-rose-100' : 'bg-gray-700 text-white' : 'text-gray-300 hover:bg-gray-800'}`}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        </>)}
      </form>

      {/* Desktop table */}
      <div className="hidden md:block bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 text-xs uppercase border-b border-gray-700">
              <th className="px-3 py-3 text-center w-10" onClick={e => e.stopPropagation()}>
                <input
                  type="checkbox"
                  checked={leads.length > 0 && leads.every(l => selectedKeys.has(selKey(l)))}
                  onChange={toggleSelectAll}
                  className="accent-blue-500 cursor-pointer"
                  title="Select all on page"
                />
              </th>
              <th className="px-5 py-3 text-left cursor-pointer hover:text-white" onClick={() => toggleSort('address')}>
                Address <SortIcon col="address" sortKey={sortKey} sortDir={sortDir} />
              </th>
              <th className="px-5 py-3 text-left cursor-pointer hover:text-white" onClick={() => toggleSort('city')}>
                City <SortIcon col="city" sortKey={sortKey} sortDir={sortDir} />
              </th>
              <th className="px-5 py-3 text-left cursor-pointer hover:text-white" onClick={() => toggleSort('county')}>
                County <SortIcon col="county" sortKey={sortKey} sortDir={sortDir} />
              </th>
              <th className="px-5 py-3 text-left cursor-pointer hover:text-white" onClick={() => toggleSort('owner_name')}>
                Owner <SortIcon col="owner_name" sortKey={sortKey} sortDir={sortDir} />
              </th>
              <th className="px-5 py-3 text-right cursor-pointer hover:text-white" onClick={() => toggleSort('assessed_value')}>
                Property Value <SortIcon col="assessed_value" sortKey={sortKey} sortDir={sortDir} />
              </th>
              <th className="px-5 py-3 text-right cursor-pointer hover:text-white" onClick={() => toggleSort('score')}>
                Score <SortIcon col="score" sortKey={sortKey} sortDir={sortDir} />
              </th>
              <th className="px-5 py-3 text-center cursor-pointer hover:text-white" onClick={() => toggleSort('rank')}>
                Rank <SortIcon col="rank" sortKey={sortKey} sortDir={sortDir} />
              </th>
              <th className="px-5 py-3 text-right">Signals</th>
              <th className="px-5 py-3 text-right cursor-pointer hover:text-white" onClick={() => toggleSort('last_updated')}>
                Updated <SortIcon col="last_updated" sortKey={sortKey} sortDir={sortDir} />
              </th>
            </tr>
          </thead>
          <tbody>
            {leads.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-5 py-10 text-center text-gray-400">
                  {activeFilterCount > 0 ? 'No leads match your filters.' : 'No leads found.'}
                </td>
              </tr>
            ) : (
              leads.map(lead => (
                <tr
                  key={`${lead.county}:${lead.parcel_id}`}
                  onClick={() => navigateToLead(lead)}
                  className={`border-t border-gray-700 hover:bg-gray-700/50 cursor-pointer transition-colors ${selectedKeys.has(selKey(lead)) ? 'bg-blue-900/20' : ''}`}
                >
                  <td className="px-3 py-3 text-center" onClick={e => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selectedKeys.has(selKey(lead))}
                      onChange={e => toggleSelect(e, lead)}
                      className="accent-blue-500 cursor-pointer"
                    />
                  </td>
                  <td className="px-5 py-3 text-white">{lead.address || 'Address unavailable'}</td>
                  <td className="px-5 py-3 text-gray-300">{lead.city ?? '—'}</td>
                  <td className="px-5 py-3 text-gray-300">{formatCounty(lead.county)}</td>
                  <td className="px-5 py-3 text-gray-300">{lead.owner_name ?? '—'}</td>
                  <td className="px-5 py-3 text-right font-mono text-gray-300">{formatCurrency(lead.assessed_value)}</td>
                  <td className="px-5 py-3 text-right font-mono text-white">{lead.score}</td>
                  <td className="px-5 py-3 text-center"><RankBadge rank={lead.rank} /></td>
                  <td className="px-5 py-3">
                    {lead.signals.length === 0 ? (
                      <div className="text-right text-gray-500">—</div>
                    ) : (
                      <div className="flex flex-wrap justify-end gap-1">
                        {lead.signals.slice(0, 2).map(signal => (
                          <span key={signal} className="rounded-full bg-blue-500/10 px-2 py-1 text-[11px] text-blue-100">
                            {getSignalLabel(signal)}
                          </span>
                        ))}
                        {lead.signals.length > 2 && (
                          <span className="rounded-full bg-gray-700 px-2 py-1 text-[11px] text-gray-300">
                            +{lead.signals.length - 2}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-5 py-3 text-right text-gray-400 text-xs">
                    {lead.last_updated ? new Date(lead.last_updated).toLocaleDateString() : '-'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Mobile sort bar */}
      <div className="md:hidden flex items-center gap-2 overflow-x-auto pb-1">
        <span className="text-gray-400 text-xs flex-shrink-0">Sort:</span>
        {([
          { key: 'score', label: 'Score' },
          { key: 'rank', label: 'Rank' },
          { key: 'assessed_value', label: 'Value' },
          { key: 'owner_name', label: 'Owner' },
          { key: 'last_updated', label: 'Updated' },
        ] as { key: SortKey; label: string }[]).map(({ key, label }) => (
          <button
            key={key}
            onClick={() => toggleSort(key)}
            className={`flex-shrink-0 rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              sortKey === key ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300'
            }`}
          >
            {label}{sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
          </button>
        ))}
      </div>

      {/* Mobile card list */}
      <div className="md:hidden space-y-2">
        {leads.length === 0 ? (
          <div className="bg-gray-800 rounded-lg border border-gray-700 px-5 py-10 text-center text-gray-400">
            {activeFilterCount > 0 ? 'No leads match your filters.' : 'No leads found.'}
          </div>
        ) : (
          leads.map(lead => (
            <div
              key={`${lead.county}:${lead.parcel_id}`}
              onClick={() => navigateToLead(lead)}
              className={`rounded-lg border px-4 py-3 cursor-pointer transition-colors ${selectedKeys.has(selKey(lead)) ? 'bg-blue-900/20 border-blue-700/50 active:bg-blue-900/30' : 'bg-gray-800 border-gray-700 active:bg-gray-700/70'}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-start gap-2 min-w-0">
                  <div onClick={e => toggleSelect(e, lead)} className="flex-shrink-0 mt-0.5 p-0.5">
                    <input
                      type="checkbox"
                      checked={selectedKeys.has(selKey(lead))}
                      onChange={() => {}}
                      className="accent-blue-500 cursor-pointer"
                    />
                  </div>
                  <div className="min-w-0">
                    <p className="text-white text-sm font-medium truncate">{lead.address || 'Address unavailable'}</p>
                    <p className="text-gray-400 text-xs mt-0.5">{[lead.city, formatCounty(lead.county)].filter(Boolean).join(' · ')}</p>
                    {lead.owner_name && <p className="text-gray-500 text-xs mt-0.5 truncate">{lead.owner_name}</p>}
                  </div>
                </div>
                <div className="flex-shrink-0 flex flex-col items-end gap-1">
                  <RankBadge rank={lead.rank} />
                  <span className="text-white font-mono text-sm font-bold">{lead.score}</span>
                </div>
              </div>
              <div className="mt-2 flex items-center gap-3 text-xs text-gray-400">
                <span>{lead.signal_count} signal{lead.signal_count !== 1 ? 's' : ''}</span>
                {lead.assessed_value != null && <span>{formatCurrency(lead.assessed_value)}</span>}
                <span className="ml-auto">{lead.last_updated ? new Date(lead.last_updated).toLocaleDateString() : ''}</span>
              </div>
              {lead.signals.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {lead.signals.slice(0, 3).map(signal => (
                    <span key={signal} className="rounded-full bg-blue-500/10 px-2 py-1 text-[11px] text-blue-100">
                      {getSignalLabel(signal)}
                    </span>
                  ))}
                  {lead.signals.length > 3 && (
                    <span className="rounded-full bg-gray-700 px-2 py-1 text-[11px] text-gray-300">
                      +{lead.signals.length - 3}
                    </span>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-gray-400">
          <span>Showing {offset + 1}-{offset + currentPageCount} of {total}</span>
          <div className="flex gap-2">
            <button
              onClick={() => navigate({ page: String(Math.max(1, page - 1)), page_size: String(pageSize) })}
              disabled={page === 1}
              className="px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Prev
            </button>
            <span className="px-3 py-1">Page {page} of {totalPages}</span>
            <button
              onClick={() => navigate({ page: String(Math.min(totalPages, page + 1)), page_size: String(pageSize) })}
              disabled={page === totalPages}
              className="px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
