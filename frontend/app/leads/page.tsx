import LeadsTable from '../../components/LeadsTable';

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

async function getLeads(): Promise<Lead[]> {
  try {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
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
          <h1 className="text-2xl font-bold text-white">Lead Feed</h1>
          <p className="text-gray-400 text-sm mt-1">
            {leads.length > 0 ? `${leads.length} properties scored` : 'No leads yet'}
          </p>
        </div>
      </div>
      <LeadsTable leads={leads} />
    </div>
  );
}
