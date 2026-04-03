"use client";

import { useEffect, useState } from "react";

// ── Types ────────────────────────────────────────────────────────────────────

interface Lead {
  property_id: string;
  parcel_id: string;
  address: string;
  city: string;
  owner_name: string | null;
  score: number;
  rank: "A" | "B" | "C";
  signals: Record<string, boolean>;
  tags: string[];
  last_updated: string;
}

interface LeadsResponse {
  leads: Lead[];
  total: number;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const COLUMNS = [
  "Parcel ID",
  "Address",
  "City",
  "Owner",
  "Score",
  "Rank",
  "Signals",
  "Last Updated",
];

const RANK_STYLES: Record<string, string> = {
  A: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  B: "bg-amber-50 text-amber-700 ring-amber-600/20",
  C: "bg-gray-100 text-gray-600 ring-gray-500/20",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function RankBadge({ rank }: { rank: string }) {
  const cls = RANK_STYLES[rank] ?? RANK_STYLES["C"];
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${cls}`}
    >
      {rank}
    </span>
  );
}

function SignalTags({ tags }: { tags: string[] }) {
  if (!tags.length) {
    return <span className="text-gray-300">—</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {tags.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium bg-blue-50 text-blue-700 ring-1 ring-inset ring-blue-600/20"
        >
          {tag.replace(/_/g, " ")}
        </span>
      ))}
    </div>
  );
}

// ── LeadsTable component ──────────────────────────────────────────────────────

export default function LeadsTable() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchLeads() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/api/leads/top", {
          cache: "no-store",
        });
        if (!res.ok) {
          throw new Error(`API error: ${res.status} ${res.statusText}`);
        }
        const data: LeadsResponse = await res.json();
        if (!cancelled) {
          setLeads(data.leads ?? []);
          setTotal(data.total ?? 0);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load leads.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchLeads();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      {/* Status bar */}
      {!loading && !error && (
        <div className="border-b border-gray-100 bg-gray-50 px-4 py-2 text-xs text-gray-500">
          {total === 0
            ? "No scored leads yet — run the scoring job to populate."
            : `Showing ${leads.length} of ${total} leads`}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              {COLUMNS.map((col) => (
                <th
                  key={col}
                  className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {/* Loading state */}
            {loading && (
              <tr>
                <td colSpan={COLUMNS.length} className="px-4 py-10 text-center">
                  <div className="flex flex-col items-center gap-2 text-gray-400">
                    <svg
                      className="h-5 w-5 animate-spin"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8v8H4z"
                      />
                    </svg>
                    <span className="text-sm">Loading leads…</span>
                  </div>
                </td>
              </tr>
            )}

            {/* Error state */}
            {!loading && error && (
              <tr>
                <td colSpan={COLUMNS.length} className="px-4 py-10 text-center">
                  <div className="flex flex-col items-center gap-2">
                    <span className="text-xl">⚠</span>
                    <p className="text-sm font-medium text-red-600">{error}</p>
                    <p className="text-xs text-gray-400">
                      Make sure the FastAPI backend is running.
                    </p>
                  </div>
                </td>
              </tr>
            )}

            {/* Empty state */}
            {!loading && !error && leads.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length} className="px-4 py-12 text-center">
                  <div className="flex flex-col items-center gap-2">
                    <span className="text-2xl">◈</span>
                    <p className="font-medium text-gray-500">No leads yet</p>
                    <p className="text-xs text-gray-400 max-w-xs">
                      Run{" "}
                      <code className="rounded bg-gray-100 px-1 py-0.5 font-mono text-[11px]">
                        scripts/run_scoring.py
                      </code>{" "}
                      after ingesting properties to populate scored leads here.
                    </p>
                  </div>
                </td>
              </tr>
            )}

            {/* Data rows */}
            {!loading &&
              !error &&
              leads.map((lead) => (
                <tr
                  key={lead.property_id}
                  className="hover:bg-gray-50 transition-colors"
                >
                  <td className="px-4 py-3 font-mono text-xs text-gray-500">
                    {lead.parcel_id}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-900">
                    {lead.address}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {lead.city}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {lead.owner_name ?? <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-4 py-3 text-sm font-semibold text-gray-900">
                    {lead.score}
                  </td>
                  <td className="px-4 py-3">
                    <RankBadge rank={lead.rank} />
                  </td>
                  <td className="px-4 py-3">
                    <SignalTags tags={lead.tags} />
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">
                    {formatDate(lead.last_updated)}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
