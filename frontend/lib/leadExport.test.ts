import { describe, expect, it, vi } from 'vitest';

import { buildLeadExportRows, fetchAllLeadExportRows, type LeadExportRecord } from './leadExport';

function okJson(payload: unknown) {
  return {
    ok: true,
    status: 200,
    async json() {
      return payload;
    },
  };
}

describe('fetchAllLeadExportRows', () => {
  it('pages through the lead API and keeps all matching rows', async () => {
    const firstPageLeads: LeadExportRecord[] = Array.from({ length: 250 }, (_, idx) => ({
      county: 'jefferson',
      parcel_id: `p1-${idx}`,
      address: '123 Main St',
      city: 'Birmingham',
      state: 'AL',
      zip: '35203',
      owner_name: 'Owner One',
      mailing_address: 'PO Box 1',
      assessed_value: 100000,
      score: 35,
      rank: 'A',
      signal_count: 2,
      signals: ['absentee_owner', 'tax_delinquent'],
      last_updated: '2026-04-21T00:00:00Z',
    }));

    const secondPageLeads: LeadExportRecord[] = Array.from({ length: 5 }, (_, idx) => ({
      ...firstPageLeads[0],
      parcel_id: `p2-${idx}`,
    }));

    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(okJson({ leads: firstPageLeads, total: 255 }))
      .mockResolvedValueOnce(okJson({ leads: secondPageLeads, total: 255 }));
    const onPage = vi.fn();

    const result = await fetchAllLeadExportRows<LeadExportRecord>({
      baseUrl: 'https://dev-rse.vercel.app',
      filters: { county: 'jefferson', signals: 'absentee_owner,tax_delinquent' },
      fetcher,
      onPage,
    });

    expect(fetcher).toHaveBeenCalledTimes(2);

    const firstUrl = new URL(fetcher.mock.calls[0][0]);
    expect(firstUrl.searchParams.get('limit')).toBe('250');
    expect(firstUrl.searchParams.get('offset')).toBe('0');
    expect(firstUrl.searchParams.get('county')).toBe('jefferson');
    expect(firstUrl.searchParams.get('signals')).toBe('absentee_owner,tax_delinquent');

    const secondUrl = new URL(fetcher.mock.calls[1][0]);
    expect(secondUrl.searchParams.get('offset')).toBe('250');

    expect(result.total).toBe(255);
    expect(result.leads).toHaveLength(255);
    expect(onPage).toHaveBeenNthCalledWith(1, { pageNumber: 1, fetched: 250, total: 255 });
    expect(onPage).toHaveBeenNthCalledWith(2, { pageNumber: 2, fetched: 255, total: 255 });
  });
});

describe('buildLeadExportRows', () => {
  it('normalizes active signals into a single export column', () => {
    const rows = buildLeadExportRows([
      {
        county: 'shelby',
        parcel_id: 'abc',
        address: '123 Oak St',
        city: 'Hoover',
        state: 'AL',
        zip: '35244',
        owner_name: 'Owner Two',
        mailing_address: 'PO Box 44',
        assessed_value: 225000,
        score: 28,
        rank: 'A',
        signal_count: 2,
        signals: ['absentee_owner', 'corporate_owner'],
        last_updated: '2026-04-21T10:00:00Z',
      },
    ]);

    expect(rows[0].active_signals).toBe('absentee_owner | corporate_owner');
    expect(rows[0].mailing_address).toBe('PO Box 44');
  });
});