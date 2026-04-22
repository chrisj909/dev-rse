export interface MapLeadRecord {
  lat: number | null;
  lng: number | null;
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

export interface MapLeadsPageProgress {
  pageNumber: number;
  fetched: number;
  total: number;
}

interface FetchMapLeadsParams {
  baseUrl: string;
  rank?: string;
  county?: string;
  search?: string;
  signals?: string;
  excludeSignals?: string;
  signalMatch?: string;
  pageLimit?: number;
  maxPages?: number;
  fetcher?: FetchLike;
  onPage?: (progress: MapLeadsPageProgress) => void;
}

export async function fetchMapLeads<TLead extends MapLeadRecord>(
  params: FetchMapLeadsParams,
): Promise<{ leads: TLead[]; total: number }> {
  const {
    baseUrl,
    rank = "",
    county = "",
    search = "",
    signals = "",
    excludeSignals = "",
    signalMatch = "all",
    pageLimit = 250,
    maxPages = 20,
    fetcher = (input) => fetch(input),
    onPage,
  } = params;

  const collected: TLead[] = [];
  let totalCount = 0;
  let offset = 0;

  for (let page = 0; page < maxPages; page += 1) {
    const query = new URLSearchParams({
      limit: String(pageLimit),
      offset: String(offset),
    });

    if (rank) query.set("rank", rank);
    if (county) query.set("county", county);
    if (search) query.set("search", search);
    if (signals) query.set("signals", signals);
    if (excludeSignals) query.set("exclude_signals", excludeSignals);
    if (signals && signalMatch !== "all") query.set("signal_match", signalMatch);

    const response = await fetcher(`${baseUrl}/api/leads?${query.toString()}`);
    if (!response.ok) {
      throw new Error(`Unable to load map leads (HTTP ${response.status}).`);
    }

    const payload = (await response.json()) as LeadsApiResponse<TLead>;
    const pageLeads = Array.isArray(payload.leads) ? payload.leads : [];

    if (page === 0) {
      totalCount = typeof payload.total === "number" ? payload.total : pageLeads.length;
    }

    collected.push(...pageLeads.filter((lead) => lead.lat != null && lead.lng != null));

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
