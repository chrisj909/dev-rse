import LeadsTable from '../../components/LeadsTable';

import { getServerApiBaseUrl } from '../../lib/server-api';

export const dynamic = 'force-dynamic';

interface Lead {
  county: string;
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
  limit: number;
  offset: number;
}

const DEFAULT_PAGE_SIZE = 50;

type LeadsPageSearchParams = {
  page?: string;
  page_size?: string;
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
  sort_by?: string;
  sort_dir?: string;
};

function buildLeadsQuery(searchParams: LeadsPageSearchParams) {
  const page = Math.max(1, Number(searchParams.page ?? '1') || 1);
  const pageSize = Math.min(250, Math.max(25, Number(searchParams.page_size ?? `${DEFAULT_PAGE_SIZE}`) || DEFAULT_PAGE_SIZE));
  const query = new URLSearchParams({
    limit: String(pageSize),
    offset: String((page - 1) * pageSize),
  });

  const keys: Array<keyof LeadsPageSearchParams> = [
    'search',
    'county',
    'city',
    'owner',
    'parcel_id',
    'min_score',
    'max_score',
    'min_value',
    'max_value',
    'rank',
    'sort_by',
    'sort_dir',
  ];

  for (const key of keys) {
    const value = searchParams[key]?.trim();
    if (value) {
      query.set(key, value);
    }
  }

  return { query, page, pageSize };
}

async function getLeads(searchParams: LeadsPageSearchParams): Promise<LeadsResponse> {
  try {
    const baseUrl = await getServerApiBaseUrl();
    const { query, pageSize } = buildLeadsQuery(searchParams);
    const res = await fetch(`${baseUrl}/api/leads?${query.toString()}`, { cache: 'no-store' });
    if (!res.ok) return { leads: [], total: 0, limit: pageSize, offset: 0 };
    const data: LeadsResponse | Lead[] = await res.json();
    if (Array.isArray(data)) {
      return { leads: data, total: data.length, limit: pageSize, offset: 0 };
    }
    return {
      leads: data.leads ?? [],
      total: data.total ?? data.leads?.length ?? 0,
      limit: data.limit ?? pageSize,
      offset: data.offset ?? 0,
    };
  } catch {
    return { leads: [], total: 0, limit: DEFAULT_PAGE_SIZE, offset: 0 };
  }
}

export default async function LeadsPage({
  searchParams,
}: {
  searchParams: Promise<LeadsPageSearchParams>;
}) {
  const resolvedSearchParams = await searchParams;
  const { leads, total, limit, offset } = await getLeads(resolvedSearchParams);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Lead Feed</h1>
          <p className="text-slate-500 text-sm mt-1">
            {total > 0 ? `${total} properties scored across Shelby and Jefferson counties` : 'No leads yet'}
          </p>
        </div>
      </div>
      <LeadsTable leads={leads} total={total} pageSize={limit} offset={offset} initialFilters={resolvedSearchParams} />
    </div>
  );
}
