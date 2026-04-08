—import LeadsTable from "@/components/LeadsTable";

export default function LeadsPage() {
  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Leads</h1>
          <p className="mt-1 text-sm text-gray-500">
            Top-ranked properties by signal score — Shelby County, AL
          </p>
        </div>
      </div>

      {/* Leads table */}
      <LeadsTable />
    </div>
  );
}
