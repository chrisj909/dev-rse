import LeadsTable from '../../components/LeadsTable';

import { getServerApiBaseUrl } from '../../lib/api';

interface Lead {
  parcel_id: string;
  address: string;
  city: string;
  owner_name: string;
  score: number;
  rank: string;
  signal_count: number;
  signals: string[];
  last_updated: string;
}

async function getLeads(): Promise<Lead[]> {
  try {
    const baseUrl = getServerApiBaseUrl();
    const res = await fetch(`${baseUrl}/api/leads`, { cache: 'no-store' });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : (data.leads ?? []);
  } catch {
    return [];
  }
}

export default async function LeadsPage() {
  const leads = await getLeads();

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Lead Feed</h1>
          <p className="text-slate-500 text-sm mt-1">
            {leads.length > 0 ? `${leads.length} properties scored` : 'No leads yet'}
          </p>
        </div>
      </div>
      <LeadsTable leads={leads} />
    </div>
  );
}
