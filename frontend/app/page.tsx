'use client';
import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';

import { getClientApiBaseUrl } from '../lib/api';
import { DEFAULT_SCORING_MODE, SCORING_MODES, getScoringModeLabel, normalizeScoringMode } from '../lib/scoringModes';

interface Lead {
  county: string;
  parcel_id: string;
  address: string | null;
  city: string | null;
  owner_name: string | null;
  score: number;
  rank: string;
  scoring_mode: string;
  signal_count: number;
  signals: string[];
  last_updated: string;
}

interface LeadsResponse {
  leads: Lead[];
  total: number;
}

const LEADS_FETCH_LIMIT = 250;

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

export default function Dashboard() {
  const router = useRouter();
  const pathname = usePathname();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [scoringMode, setScoringModeState] = useState(DEFAULT_SCORING_MODE);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    setScoringModeState(normalizeScoringMode(new URLSearchParams(window.location.search).get('scoring_mode')));
  }, []);

  const fetchLeads = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        limit: String(LEADS_FETCH_LIMIT),
        scoring_mode: scoringMode,
      });
      const res = await fetch(`${getClientApiBaseUrl()}/api/leads?${params.toString()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: LeadsResponse | Lead[] = await res.json();
      if (Array.isArray(data)) {
        setLeads(data);
        setTotal(data.length);
      } else {
        setLeads(data.leads ?? []);
        setTotal(data.total ?? data.leads?.length ?? 0);
      }
      setLastRefresh(new Date());
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load leads');
    } finally {
      setLoading(false);
    }
  }, [scoringMode]);

  useEffect(() => {
    fetchLeads();
    const interval = setInterval(fetchLeads, 60000);
    return () => clearInterval(interval);
  }, [fetchLeads]);

  const totalProperties = total;
  const rankACount = leads.filter(l => l.rank === 'A').length;
  const totalSignals = leads.reduce((sum, l) => sum + (l.signal_count ?? 0), 0);
  const top5 = [...leads].sort((a, b) => b.score - a.score).slice(0, 5);

  function setMode(nextMode: string) {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    if (nextMode === DEFAULT_SCORING_MODE) {
      params.delete('scoring_mode');
    } else {
      params.set('scoring_mode', nextMode);
    }
    const query = params.toString();
    setScoringModeState(normalizeScoringMode(nextMode));
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Real Estate Signal Engine</h1>
          <p className="text-slate-500 text-sm mt-1">Shelby + Jefferson Counties, AL — {getScoringModeLabel(scoringMode)} Dashboard</p>
        </div>
        <div className="text-right">
          <label className="block text-xs uppercase tracking-wide text-gray-500">Scoring Lens</label>
          <select
            value={scoringMode}
            onChange={e => setMode(e.target.value)}
            className="mt-1 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-slate-700"
          >
            {SCORING_MODES.map(mode => (
              <option key={mode.value} value={mode.value}>{mode.label}</option>
            ))}
          </select>
          {lastRefresh && (
            <p className="text-xs text-gray-500">Last updated: {lastRefresh.toLocaleTimeString()}</p>
          )}
          <button onClick={fetchLeads} className="mt-1 text-xs text-blue-400 hover:text-blue-300 underline">
            Refresh now
          </button>
        </div>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-800 rounded-lg p-5 border border-gray-700">
          <p className="text-gray-400 text-sm uppercase tracking-wide">Total Properties</p>
          <p className="text-3xl font-bold text-white mt-2">{loading ? '—' : totalProperties.toLocaleString()}</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-5 border border-gray-700">
          <p className="text-gray-400 text-sm uppercase tracking-wide">Signals Detected</p>
          <p className="text-3xl font-bold text-white mt-2">{loading ? '—' : totalSignals.toLocaleString()}</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-5 border border-gray-700">
          <p className="text-gray-400 text-sm uppercase tracking-wide">Top Leads (Rank A)</p>
          <p className="text-3xl font-bold text-green-400 mt-2">{loading ? '—' : rankACount.toLocaleString()}</p>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-900/40 border border-red-700 rounded-lg p-4 text-red-300 text-sm">
          Unable to load data: {error}
        </div>
      )}

      {/* Top 5 Leads */}
      <div className="bg-gray-800 rounded-lg border border-gray-700">
        <div className="px-5 py-4 border-b border-gray-700 flex items-center justify-between">
          <h2 className="text-white font-semibold">Top 5 Leads by Score</h2>
          <Link href={scoringMode === DEFAULT_SCORING_MODE ? '/leads' : `/leads?scoring_mode=${encodeURIComponent(scoringMode)}`} className="text-blue-400 hover:text-blue-300 text-sm">View all →</Link>
        </div>
        {loading ? (
          <div className="p-5 space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-10 bg-gray-700 rounded animate-pulse" />
            ))}
          </div>
        ) : top5.length === 0 ? (
          <div className="p-8 text-center text-gray-400">
            <p>No leads yet.</p>
            <p className="text-sm mt-1">Connect a data source to begin ingesting properties and running signal detection.</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 text-xs uppercase">
                <th className="px-5 py-3 text-left">Address</th>
                <th className="px-5 py-3 text-left">City</th>
                <th className="px-5 py-3 text-right">Score</th>
                <th className="px-5 py-3 text-center">Rank</th>
                <th className="px-5 py-3 text-right">Signals</th>
              </tr>
            </thead>
            <tbody>
              {top5.map(lead => (
                <tr
                  key={`${lead.county}:${lead.parcel_id}`}
                  onClick={() => {
                    const params = new URLSearchParams({
                      parcel_id: lead.parcel_id,
                      county: lead.county,
                    });
                    if (scoringMode !== DEFAULT_SCORING_MODE) {
                      params.set('scoring_mode', scoringMode);
                    }
                    window.location.href = `/property?${params.toString()}`;
                  }}
                  className="border-t border-gray-700 hover:bg-gray-700/50 cursor-pointer transition-colors"
                >
                  <td className="px-5 py-3 text-white">{lead.address || 'Address unavailable'}</td>
                  <td className="px-5 py-3 text-gray-300">{lead.city ?? '—'}</td>
                  <td className="px-5 py-3 text-right text-white font-mono">{lead.score}</td>
                  <td className="px-5 py-3 text-center"><RankBadge rank={lead.rank} /></td>
                  <td className="px-5 py-3 text-right text-gray-300">{lead.signal_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
