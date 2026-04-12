'use client';
import { useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';

interface Lead {
  parcel_id: string;
  address: string | null;
  city: string | null;
  owner_name: string | null;
  assessed_value: number | null;
  score: number;
  rank: string;
  signal_count: number;
  last_updated: string;
}

type SortKey = 'score' | 'address' | 'city' | 'assessed_value' | 'last_updated';
type SortDir = 'asc' | 'desc';

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

const PAGE_SIZE = 25;

export default function LeadsTable({ leads }: { leads: Lead[] }) {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [cityFilter, setCityFilter] = useState('');
  const [ownerFilter, setOwnerFilter] = useState('');
  const [parcelFilter, setParcelFilter] = useState('');
  const [minScore, setMinScore] = useState('');
  const [maxScore, setMaxScore] = useState('');
  const [minValue, setMinValue] = useState('');
  const [maxValue, setMaxValue] = useState('');
  const [rankFilter, setRankFilter] = useState<string>('All');
  const [sortKey, setSortKey] = useState<SortKey>('score');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [page, setPage] = useState(1);

  const activeFilterCount = [
    search,
    cityFilter,
    ownerFilter,
    parcelFilter,
    minScore,
    maxScore,
    minValue,
    maxValue,
    rankFilter !== 'All' ? rankFilter : '',
  ].filter(Boolean).length;

  const filtered = useMemo(() => {
    let result = leads;
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(l =>
        l.address?.toLowerCase().includes(q) || l.owner_name?.toLowerCase().includes(q)
        || l.parcel_id.toLowerCase().includes(q)
      );
    }
    if (cityFilter.trim()) {
      const q = cityFilter.toLowerCase();
      result = result.filter(l => l.city?.toLowerCase().includes(q));
    }
    if (ownerFilter.trim()) {
      const q = ownerFilter.toLowerCase();
      result = result.filter(l => l.owner_name?.toLowerCase().includes(q));
    }
    if (parcelFilter.trim()) {
      const q = parcelFilter.toLowerCase();
      result = result.filter(l => l.parcel_id.toLowerCase().includes(q));
    }
    if (rankFilter !== 'All') {
      result = result.filter(l => l.rank === rankFilter);
    }
    if (minScore.trim()) {
      const floor = Number(minScore);
      if (!Number.isNaN(floor)) {
        result = result.filter(l => l.score >= floor);
      }
    }
    if (maxScore.trim()) {
      const ceiling = Number(maxScore);
      if (!Number.isNaN(ceiling)) {
        result = result.filter(l => l.score <= ceiling);
      }
    }
    if (minValue.trim()) {
      const floor = Number(minValue);
      if (!Number.isNaN(floor)) {
        result = result.filter(l => (l.assessed_value ?? -1) >= floor);
      }
    }
    if (maxValue.trim()) {
      const ceiling = Number(maxValue);
      if (!Number.isNaN(ceiling)) {
        result = result.filter(l => (l.assessed_value ?? Number.MAX_SAFE_INTEGER) <= ceiling);
      }
    }
    result = [...result].sort((a, b) => {
      let av: string | number = a[sortKey] ?? '';
      let bv: string | number = b[sortKey] ?? '';
      if (typeof av === 'string') av = av.toLowerCase();
      if (typeof bv === 'string') bv = bv.toLowerCase();
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return result;
  }, [
    leads,
    search,
    cityFilter,
    ownerFilter,
    parcelFilter,
    rankFilter,
    minScore,
    maxScore,
    minValue,
    maxValue,
    sortKey,
    sortDir,
  ]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('desc'); }
    setPage(1);
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
    setCityFilter('');
    setOwnerFilter('');
    setParcelFilter('');
    setMinScore('');
    setMaxScore('');
    setMinValue('');
    setMaxValue('');
    setRankFilter('All');
    setPage(1);
  }

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-gray-700 bg-gray-800/95 p-5 shadow-[0_18px_45px_rgba(15,23,42,0.28)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-300">Detailed Search</p>
            <h2 className="mt-1 text-lg font-semibold text-white">Refine the lead feed</h2>
            <p className="mt-1 text-sm text-gray-400">Search across parcel, owner, value, score, and location without leaving the page.</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 text-xs font-medium text-blue-200">
              {filtered.length} matches
            </div>
            <div className="rounded-full border border-gray-600 bg-gray-700/80 px-3 py-1 text-xs font-medium text-gray-300">
              {activeFilterCount} active filters
            </div>
            <button
              onClick={clearFilters}
              className="rounded-full border border-gray-600 px-3 py-1 text-xs font-medium text-gray-300 transition-colors hover:border-gray-500 hover:bg-gray-700"
            >
              Reset
            </button>
          </div>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">Global Search</span>
            <input
              type="text"
              placeholder="Address, owner, or parcel"
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1); }}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">City</span>
            <input
              type="text"
              placeholder="Leeds, Birmingham..."
              value={cityFilter}
              onChange={e => { setCityFilter(e.target.value); setPage(1); }}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">Owner</span>
            <input
              type="text"
              placeholder="Owner name"
              value={ownerFilter}
              onChange={e => { setOwnerFilter(e.target.value); setPage(1); }}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">Parcel ID</span>
            <input
              type="text"
              placeholder="01 6 23 ..."
              value={parcelFilter}
              onChange={e => { setParcelFilter(e.target.value); setPage(1); }}
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
              onChange={e => { setMinScore(e.target.value); setPage(1); }}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">Max Score</span>
            <input
              type="number"
              placeholder="100"
              value={maxScore}
              onChange={e => { setMaxScore(e.target.value); setPage(1); }}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">Min Value</span>
            <input
              type="number"
              placeholder="50000"
              value={minValue}
              onChange={e => { setMinValue(e.target.value); setPage(1); }}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">Max Value</span>
            <input
              type="number"
              placeholder="500000"
              value={maxValue}
              onChange={e => { setMaxValue(e.target.value); setPage(1); }}
              className="w-full rounded-xl border border-gray-600 bg-gray-900/80 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <div>
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-400">Rank</span>
            <div className="flex gap-2">
              {['All', 'A', 'B', 'C'].map(r => (
                <button
                  key={r}
                  onClick={() => { setRankFilter(r); setPage(1); }}
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
      </div>

      {/* Table */}
      <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 text-xs uppercase border-b border-gray-700">
              <th className="px-5 py-3 text-left cursor-pointer hover:text-white" onClick={() => toggleSort('address')}>
                Address <SortIcon col="address" sortKey={sortKey} sortDir={sortDir} />
              </th>
              <th className="px-5 py-3 text-left cursor-pointer hover:text-white" onClick={() => toggleSort('city')}>
                City <SortIcon col="city" sortKey={sortKey} sortDir={sortDir} />
              </th>
              <th className="px-5 py-3 text-left">Owner</th>
              <th className="px-5 py-3 text-right cursor-pointer hover:text-white" onClick={() => toggleSort('assessed_value')}>
                Property Value <SortIcon col="assessed_value" sortKey={sortKey} sortDir={sortDir} />
              </th>
              <th className="px-5 py-3 text-right cursor-pointer hover:text-white" onClick={() => toggleSort('score')}>
                Score <SortIcon col="score" sortKey={sortKey} sortDir={sortDir} />
              </th>
              <th className="px-5 py-3 text-center">Rank</th>
              <th className="px-5 py-3 text-right">Signals</th>
              <th className="px-5 py-3 text-right cursor-pointer hover:text-white" onClick={() => toggleSort('last_updated')}>
                Updated <SortIcon col="last_updated" sortKey={sortKey} sortDir={sortDir} />
              </th>
            </tr>
          </thead>
          <tbody>
            {paginated.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-5 py-10 text-center text-gray-400">
                  {search || rankFilter !== 'All' ? 'No leads match your filters.' : 'No leads found.'}
                </td>
              </tr>
            ) : (
              paginated.map(lead => (
                <tr
                  key={lead.parcel_id}
                  onClick={() => router.push(`/property?parcel_id=${encodeURIComponent(lead.parcel_id)}`)}
                  className="border-t border-gray-700 hover:bg-gray-700/50 cursor-pointer transition-colors"
                >
                  <td className="px-5 py-3 text-white">{lead.address || 'Address unavailable'}</td>
                  <td className="px-5 py-3 text-gray-300">{lead.city ?? '—'}</td>
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

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-gray-400">
          <span>Showing {(page - 1) * PAGE_SIZE + 1}-{Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}</span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Prev
            </button>
            <span className="px-3 py-1">Page {page} of {totalPages}</span>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
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
