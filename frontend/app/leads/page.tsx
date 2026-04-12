import LeadsTable from '../../components/LeadsTable';

import { getServerApiBaseUrl } from '../../lib/server-api';

export const dynamic = 'force-dynamic';

interface Lead {
  parcel_id: string;
  address: string | null;
  city: string | null;
  owner_name: string | null;
  assessed_value: number | null;
  score: number;
  rank: string;
  signal_count: number;
  signals: string[];
  last_updated: string;
}

interface LeadsResponse {
  leads: Lead[];
  total: number;
}

const LEADS_FETCH_LIMIT = 1000;

async function getLeads(): Promise<LeadsResponse> {
  try {
    const baseUrl = await getServerApiBaseUrl();
    const res = await fetch(`${baseUrl}/api/leads?limit=${LEADS_FETCH_LIMIT}`, { cache: 'no-store' });
    if (!res.ok) return { leads: [], total: 0 };
    const data: LeadsResponse | Lead[] = await res.json();
    if (Array.isArray(data)) {
      return { leads: data, total: data.length };
    }
    return {
      leads: data.leads ?? [],
      total: data.total ?? data.leads?.length ?? 0,
    };
  } catch {
    return { leads: [], total: 0 };
  }
}

export default async function LeadsPage() {
  const { leads, total } = await getLeads();

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Lead Feed</h1>
          <p className="text-slate-500 text-sm mt-1">
            {total > 0 ? `${total} properties scored` : 'No leads yet'}
          </p>
        </div>
      </div>
      <LeadsTable leads={leads} />
    </div>
  );
}
