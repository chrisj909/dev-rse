import Link from 'next/link';
import { notFound } from 'next/navigation';

import { getServerApiBaseUrl } from '../../lib/server-api';

export const dynamic = 'force-dynamic';

interface LeadDetail {
  property_id: string;
  parcel_id: string;
  address: string | null;
  city: string | null;
  owner_name: string | null;
  mailing_address: string | null;
  assessed_value: number | null;
  state: string;
  signals: Record<string, boolean>;
  score: {
    score: number;
    rank: string;
    reason: string[];
    last_updated: string;
  };
}

async function getLead(parcelId: string): Promise<LeadDetail | null> {
  try {
    const baseUrl = await getServerApiBaseUrl();
    const res = await fetch(`${baseUrl}/api/leads/${encodeURIComponent(parcelId)}`, { cache: 'no-store' });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}

function RankBadge({ rank }: { rank: string }) {
  const colors: Record<string, string> = {
    A: 'bg-green-600 text-white',
    B: 'bg-yellow-500 text-black',
    C: 'bg-gray-500 text-white',
  };
  return (
    <span className={`px-3 py-1 rounded text-sm font-bold ${colors[rank] ?? 'bg-gray-600 text-white'}`}>
      Rank {rank}
    </span>
  );
}

export default async function PropertyPage({
  searchParams,
}: {
  searchParams: Promise<{ parcel_id?: string }>;
}) {
  const { parcel_id } = await searchParams;
  if (!parcel_id) notFound();

  const lead = await getLead(parcel_id);
  if (!lead) notFound();

  const activeSignals = Object.entries(lead.signals).filter(([, isActive]) => Boolean(isActive));

  return (
    <div className="p-6 max-w-2xl space-y-6">
      <div>
        <Link href="/leads" className="text-blue-400 hover:text-blue-300 text-sm">← Back to Leads</Link>
      </div>

      <div>
        <h1 className="text-2xl font-bold text-slate-900">{lead.address || 'Address unavailable'}</h1>
        <p className="text-slate-500 mt-1">{[lead.city, lead.state].filter(Boolean).join(', ') || 'Location unavailable'}</p>
      </div>

      <div className="bg-gray-800 rounded-lg border border-gray-700 divide-y divide-gray-700">
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">Owner</span>
          <span className="text-white font-medium">{lead.owner_name ?? '—'}</span>
        </div>
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">Parcel ID</span>
          <span className="text-white font-mono text-sm">{lead.parcel_id}</span>
        </div>
        <div className="flex justify-between items-center px-5 py-4">
          <span className="text-gray-400">Score</span>
          <span className="text-white text-xl font-bold font-mono">{lead.score.score}</span>
        </div>
        <div className="flex justify-between items-center px-5 py-4">
          <span className="text-gray-400">Rank</span>
          <RankBadge rank={lead.score.rank} />
        </div>
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">Signals Detected</span>
          <span className="text-white font-medium">{activeSignals.length}</span>
        </div>
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">Mailing Address</span>
          <span className="text-white font-medium">{lead.mailing_address ?? '—'}</span>
        </div>
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">Assessed Value</span>
          <span className="text-white font-medium">{lead.assessed_value != null ? `$${lead.assessed_value.toLocaleString()}` : '—'}</span>
        </div>
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">Last Updated</span>
          <span className="text-gray-300 text-sm">
            {lead.score.last_updated ? new Date(lead.score.last_updated).toLocaleString() : '—'}
          </span>
        </div>
      </div>

      <div className="bg-gray-800 rounded-lg border border-gray-700 p-5 space-y-3">
        <h2 className="text-white font-semibold text-sm uppercase tracking-wide">Active Signals</h2>
        {activeSignals.length === 0 ? (
          <p className="text-gray-400 text-sm">No active signals on this property.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {activeSignals.map(([signalName]) => (
              <span key={signalName} className="rounded-full bg-blue-600/20 px-3 py-1 text-sm text-blue-200">
                {signalName.replaceAll('_', ' ')}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}