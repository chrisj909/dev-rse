import { describe, expect, it, vi } from "vitest";

import { fetchMapLeads, type MapLeadRecord } from "./mapLeads";

interface TestLead extends MapLeadRecord {
  id: string;
}

function okJson(payload: unknown) {
  return {
    ok: true,
    status: 200,
    async json() {
      return payload;
    },
  };
}

describe("fetchMapLeads", () => {
  it("pages using the 250 API cap and aggregates mapped leads", async () => {
    const firstPageLeads: TestLead[] = Array.from({ length: 250 }, (_, idx) => ({
      id: `p1-${idx}`,
      lat: idx === 0 ? null : 33.4,
      lng: idx === 0 ? null : -86.8,
    }));

    const secondPageLeads: TestLead[] = Array.from({ length: 50 }, (_, idx) => ({
      id: `p2-${idx}`,
      lat: 33.5,
      lng: -86.7,
    }));

    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(okJson({ leads: firstPageLeads, total: 300 }))
      .mockResolvedValueOnce(okJson({ leads: secondPageLeads, total: 300 }));
    const onPage = vi.fn();

    const result = await fetchMapLeads<TestLead>({
      baseUrl: "https://dev-rse.vercel.app",
      fetcher,
      onPage,
    });

    expect(fetcher).toHaveBeenCalledTimes(2);

    const firstUrl = new URL(fetcher.mock.calls[0][0]);
    expect(firstUrl.searchParams.get("limit")).toBe("250");
    expect(firstUrl.searchParams.get("offset")).toBe("0");

    const secondUrl = new URL(fetcher.mock.calls[1][0]);
    expect(secondUrl.searchParams.get("limit")).toBe("250");
    expect(secondUrl.searchParams.get("offset")).toBe("250");

    expect(result.total).toBe(300);
    expect(result.leads).toHaveLength(299);

    expect(onPage).toHaveBeenCalledTimes(2);
    expect(onPage).toHaveBeenNthCalledWith(1, {
      pageNumber: 1,
      fetched: 250,
      total: 300,
    });
    expect(onPage).toHaveBeenNthCalledWith(2, {
      pageNumber: 2,
      fetched: 300,
      total: 300,
    });
  });

  it("throws a useful error when API returns non-200", async () => {
    const fetcher = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      async json() {
        return { detail: "Input should be less than or equal to 250" };
      },
    });

    await expect(
      fetchMapLeads<TestLead>({
        baseUrl: "https://dev-rse.vercel.app",
        fetcher,
      }),
    ).rejects.toThrow("Unable to load map leads (HTTP 422).");
  });
});
