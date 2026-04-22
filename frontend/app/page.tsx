'use client';
import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import { getClientApiBaseUrl } from '../lib/api';

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
  const [leads, setLeads] = useState<Lead[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const fetchLeads = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        limit: String(LEADS_FETCH_LIMIT),
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
  }, []);

  useEffect(() => {
    fetchLeads();
    const interval = setInterval(fetchLeads, 60000);
    return () => clearInterval(interval);
  }, [fetchLeads]);

  const totalProperties = total;
  const rankACount = leads.filter(l => l.rank === 'A').length;
  const totalSignals = leads.reduce((sum, l) => sum + (l.signal_count ?? 0), 0);
  const top5 = [...leads].sort((a, b) => b.score - a.score).slice(0, 5);

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900 sm:text-2xl">Real Estate Signal Engine</h1>
          <p className="text-slate-500 text-sm mt-1">Shelby + Jefferson Counties, AL lead overview</p>
        </div>
        <div className="flex flex-row items-center gap-3 sm:flex-col sm:items-end sm:gap-1">
          <div className="flex items-center gap-2 text-xs text-gray-500">
            {lastRefresh && <span>{lastRefresh.toLocaleTimeString()}</span>}
            <button onClick={fetchLeads} className="text-blue-400 hover:text-blue-300 underline">Refresh</button>
          </div>
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
          <Link href="/leads" className="text-blue-400 hover:text-blue-300 text-sm">View all →</Link>
        </div>
        {loading ? (
          <div className="p-5 space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-14 bg-gray-700 rounded animate-pulse" />
            ))}
          </div>
        ) : top5.length === 0 ? (
          <div className="p-8 text-center text-gray-400">
            <p>No leads yet.</p>
            <p className="text-sm mt-1">Connect a data source to begin ingesting properties and running signal detection.</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-700">
            {top5.map(lead => {
              const params = new URLSearchParams({ parcel_id: lead.parcel_id, county: lead.county });
              return (
                <div
                  key={`${lead.county}:${lead.parcel_id}`}
                  onClick={() => router.push(`/property?${params.toString()}`)}
                  className="flex items-center gap-3 px-5 py-3 hover:bg-gray-700/50 cursor-pointer transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-sm font-medium truncate">{lead.address || 'Address unavailable'}</p>
                    <p className="text-gray-400 text-xs">{lead.city ?? '—'} · {lead.signal_count} signal{lead.signal_count !== 1 ? 's' : ''}</p>
                  </div>
                  <div className="flex-shrink-0 flex items-center gap-2">
                    <span className="text-white font-mono text-sm">{lead.score}</span>
                    <RankBadge rank={lead.rank} />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
