import Link from 'next/link';
import { notFound } from 'next/navigation';

interface Lead {
  parcel_id: string;
  address: string;
  city: string;
  owner_name: string;
  score: number;
  rank: string;
  signal_count: number;
  last_updated: string;
}

async function getLead(parcel_id: string): Promise<Lead | null> {
  try {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
    const res = await fetch(`${baseUrl}/api/leads/${parcel_id}`, { cache: 'no-store' });
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

export default async function PropertyDetail({ params }: { params: { parcel_id: string } }) {
  const lead = await getLead(params.parcel_id);
  if (!lead) notFound();

  return (
    <div className="p-6 max-w-2xl space-y-6">
      <div>
        <Link href="/leads" className="text-blue-400 hover:text-blue-300 text-sm">← Back to Leads</Link>
      </div>

      <div>
        <h1 className="text-2xl font-bold text-white">{lead.address}</h1>
        <p className="text-gray-400 mt-1">{lead.city}, AL</p>
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
          <span className="text-white text-xl font-bold font-mono">{lead.score}</span>
        </div>
        <div className="flex justify-between items-center px-5 py-4">
          <span className="text-gray-400">Rank</span>
          <RankBadge rank={lead.rank} />
        </div>
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">Signals Detected</span>
          <span className="text-white font-medium">{lead.signal_count}</span>
        </div>
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">Last Updated</span>
          <span className="text-gray-300 text-sm">
            {lead.last_updated ? new Date(lead.last_updated).toLocaleString() : '—'}
          </span>
        </div>
      </div>
    </div>
  );
}
