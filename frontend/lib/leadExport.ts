import { downloadCsv } from './exportCsv';

export interface LeadExportRecord {
  county: string;
  parcel_id: string;
  address: string | null;
  city: string | null;
  state: string;
  zip: string | null;
  owner_name: string | null;
  mailing_address: string | null;
  assessed_value: number | null;
  score: number;
  rank: string;
  signal_count: number;
  signals: string[];
  last_updated: string;
}

interface LeadsApiResponse<TLead> {
  leads?: TLead[];
  total?: number;
}

interface FetchResponseLike {
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
}

type FetchLike = (input: string) => Promise<FetchResponseLike>;

export interface LeadExportPageProgress {
  pageNumber: number;
  fetched: number;
  total: number;
}

interface FetchLeadExportParams {
  baseUrl: string;
  filters?: Record<string, string>;
  pageLimit?: number;
  maxPages?: number;
  fetcher?: FetchLike;
  onPage?: (progress: LeadExportPageProgress) => void;
}

export const LEAD_EXPORT_COLUMNS = [
  'county',
  'parcel_id',
  'address',
  'city',
  'state',
  'zip',
  'owner_name',
  'mailing_address',
  'assessed_value',
  'score',
  'rank',
  'signal_count',
  'active_signals',
  'last_updated',
] as const;

export async function fetchAllLeadExportRows<TLead extends LeadExportRecord>(
  params: FetchLeadExportParams,
): Promise<{ leads: TLead[]; total: number }> {
  const {
    baseUrl,
    filters = {},
    pageLimit = 250,
    maxPages = 200,
    fetcher = (input) => fetch(input),
    onPage,
  } = params;

  const collected: TLead[] = [];
  let totalCount = 0;
  let offset = 0;

  for (let page = 0; page < maxPages; page += 1) {
    const query = new URLSearchParams({
      ...filters,
      limit: String(pageLimit),
      offset: String(offset),
    });

    const response = await fetcher(`${baseUrl}/api/leads?${query.toString()}`);
    if (!response.ok) {
      throw new Error(`Unable to export leads (HTTP ${response.status}).`);
    }

    const payload = (await response.json()) as LeadsApiResponse<TLead>;
    const pageLeads = Array.isArray(payload.leads) ? payload.leads : [];

    if (page === 0) {
      totalCount = typeof payload.total === 'number' ? payload.total : pageLeads.length;
    }

    collected.push(...pageLeads);
    offset += pageLeads.length;

    onPage?.({
      pageNumber: page + 1,
      fetched: Math.min(offset, totalCount),
      total: totalCount,
    });

    if (pageLeads.length === 0 || pageLeads.length < pageLimit || offset >= totalCount) {
      break;
    }
  }

  return { leads: collected, total: totalCount };
}

export function buildLeadExportRows(leads: LeadExportRecord[]): Record<string, unknown>[] {
  return leads.map(lead => ({
    county: lead.county,
    parcel_id: lead.parcel_id,
    address: lead.address,
    city: lead.city,
    state: lead.state,
    zip: lead.zip,
    owner_name: lead.owner_name,
    mailing_address: lead.mailing_address,
    assessed_value: lead.assessed_value,
    score: lead.score,
    rank: lead.rank,
    signal_count: lead.signal_count,
    active_signals: lead.signals.join(' | '),
    last_updated: lead.last_updated,
  }));
}

export async function exportLeadResultsToCsv(
  filename: string,
  params: FetchLeadExportParams,
): Promise<{ total: number }> {
  const { leads, total } = await fetchAllLeadExportRows(params);
  downloadCsv(filename, buildLeadExportRows(leads), [...LEAD_EXPORT_COLUMNS]);
  return { total };
}