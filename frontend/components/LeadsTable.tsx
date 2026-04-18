'use client';
import { type FormEvent, useState, useTransition } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

import { DEFAULT_SCORING_MODE, SCORING_MODES, getScoringModeLabel } from '../lib/scoringModes';

interface Lead {
  county: string;
  parcel_id: string;
  address: string | null;
  city: string | null;
  owner_name: string | null;
  assessed_value: number | null;
  score: number;
  rank: string;
  scoring_mode?: string;
  signal_count: number;
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
  const [sortKey, setSortKey] = useState<SortKey>((initialFilters.sort_by as SortKey) ?? 'score');
  const [sortDir, setSortDir] = useState<SortDir>((initialFilters.sort_dir as SortDir) ?? 'desc');

  const page = Math.floor(offset / pageSize) + 1;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

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

  function toggleSort(key: SortKey) {
    let nextDir: SortDir = 'desc';
    if (sortKey === key) {
      nextDir = sortDir === 'asc' ? 'desc' : 'asc';
      setSortDir(nextDir);
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
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
      sort_by: sortKey,
      sort_dir: sortDir,
      page: '1',
      page_size: String(pageSize),
    });
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
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-300">Detailed Search</p>
            <h2 className="mt-1 text-lg font-semibold text-white">Refine the lead feed</h2>
            <p className="mt-1 text-sm text-gray-400">Search across parcel, owner, value, score, and location without leaving the page.</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 text-xs font-medium text-blue-200">
              {total} matches
            </div>
            <div className="rounded-full border border-gray-600 bg-gray-700/80 px-3 py-1 text-xs font-medium text-gray-300">
              {activeFilterCount} active filters
            </div>
            <div className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-200">
              {getScoringModeLabel(scoringMode)}
            </div>
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
          </div>
        </div>

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
                  onClick={() => setRankFilter(r)}
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
      </form>

      {/* Desktop table */}
      <div className="hidden md:block bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 text-xs uppercase border-b border-gray-700">
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
                <td colSpan={9} className="px-5 py-10 text-center text-gray-400">
                  {activeFilterCount > 0 ? 'No leads match your filters.' : 'No leads found.'}
                </td>
              </tr>
            ) : (
              leads.map(lead => (
                <tr
                  key={`${lead.county}:${lead.parcel_id}`}
                  onClick={() => navigateToLead(lead)}
                  className="border-t border-gray-700 hover:bg-gray-700/50 cursor-pointer transition-colors"
                >
                  <td className="px-5 py-3 text-white">{lead.address || 'Address unavailable'}</td>
                  <td className="px-5 py-3 text-gray-300">{lead.city ?? '—'}</td>
                  <td className="px-5 py-3 text-gray-300">{formatCounty(lead.county)}</td>
                  <td className="px-5 py-3 text-gray-300">{lead.owner_name ?? '—'}</td>
                  <td className="px-5 py-3 text-right font-mono text-gray-300">{formatCurrency(lead.assessed_value)}</td>
                  <td className="px-5 py-3 text-right font-mono text-white">{lead.score}</td>
                  <td className="px-5 py-3 text-center"><RankBadge rank={lead.rank} /></td>
                  <td className="px-5 py-3 text-right text-gray-300">{lead.signal_count}</td>
                  <td className="px-5 py-3 text-right text-gray-400 text-xs">
                    {lead.last_updated ? new Date(lead.last_updated).toLocaleDateString() : '-'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
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
              className="bg-gray-800 rounded-lg border border-gray-700 px-4 py-3 cursor-pointer active:bg-gray-700/70"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-white text-sm font-medium truncate">{lead.address || 'Address unavailable'}</p>
                  <p className="text-gray-400 text-xs mt-0.5">{[lead.city, formatCounty(lead.county)].filter(Boolean).join(' · ')}</p>
                  {lead.owner_name && <p className="text-gray-500 text-xs mt-0.5 truncate">{lead.owner_name}</p>}
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
