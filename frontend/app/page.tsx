import Link from "next/link";

export default function DashboardPage() {
  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-500">
          Real Estate Signal Engine — Shelby County, AL
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-3 mb-8">
        <StatCard label="Total Properties" value="—" note="Loaded after ingestion" />
        <StatCard label="Signals Detected" value="—" note="After signal run" />
        <StatCard label="Top-Ranked Leads" value="—" note="Score ≥ 25 (Rank A)" />
      </div>

      {/* Quick links */}
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="text-base font-medium text-gray-800 mb-4">Quick Access</h2>
        <div className="flex gap-4">
          <Link
            href="/leads"
            className="inline-flex items-center rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 transition-colors"
          >
            View Leads →
          </Link>
        </div>
        <p className="mt-4 text-xs text-gray-400">
          Connect a data source to begin ingesting properties and running signal detection.
        </p>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note: string;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
        {label}
      </p>
      <p className="mt-2 text-3xl font-semibold text-gray-900">{value}</p>
      <p className="mt-1 text-xs text-gray-400">{note}</p>
    </div>
  );
}
