'use client';
import { useState } from 'react';

interface IngestResult {
  status: string;
  fetched?: number;
  upserted?: number;
  signals?: { processed?: number; error?: string };
  elapsed_seconds?: number;
  sample?: unknown[];
  error?: string;
}

export default function IngestPage() {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<IngestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dryRun, setDryRun] = useState(true);
  const [delinquentOnly, setDelinquentOnly] = useState(false);
  const [limit, setLimit] = useState('100');
  const [cronSecret, setCronSecret] = useState('');

  async function runIngest() {
    setRunning(true);
    setResult(null);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (dryRun) params.set('dry_run', 'true');
      if (delinquentOnly) params.set('delinquent_only', 'true');
      if (limit) params.set('limit', limit);
      const res = await fetch(`/api/ingest/run?${params}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(cronSecret ? { 'x-cron-secret': cronSecret } : {}),
        },
      });
      const data = await res.json();
      if (!res.ok) setError(data.detail ?? JSON.stringify(data));
      else setResult(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Network error');
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="p-6 max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Data Ingestion</h1>
        <p className="text-gray-400 text-sm mt-1">Pull Shelby County property data and score leads</p>
      </div>
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-5 space-y-3">
        <h2 className="text-white font-semibold text-sm uppercase tracking-wide mb-3">Active Sources</h2>
        <div className="flex items-center gap-3">
          <span className="w-2 h-2 rounded-full bg-green-400" />
          <div>
            <p className="text-white text-sm font-medium">Shelby County ArcGIS</p>
            <p className="text-gray-400 text-xs">106,000+ parcels · owner, address, tax status, deed date</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="w-2 h-2 rounded-full bg-yellow-400" />
          <div>
            <p className="text-white text-sm font-medium">GovEase Tax Lien Auction</p>
            <p className="text-gray-400 text-xs">Active when auction cycle is live</p>
          </div>
        </div>
      </div>
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-5 space-y-4">
        <h2 className="text-white font-semibold text-sm uppercase tracking-wide">Options</h2>
        <label className="flex items-center gap-3 cursor-pointer">
          <input type="checkbox" checked={dryRun} onChange={e => setDryRun(e.target.checked)} className="w-4 h-4 rounded accent-blue-500" />
          <div>
            <p className="text-white text-sm">Dry run (preview only)</p>
            <p className="text-gray-400 text-xs">Fetch data but don&apos;t write to database</p>
          </div>
        </label>
        <label className="flex items-center gap-3 cursor-pointer">
          <input type="checkbox" checked={delinquentOnly} onChange={e => setDelinquentOnly(e.target.checked)} className="w-4 h-4 rounded accent-blue-500" />
          <div>
            <p className="text-white text-sm">Delinquent only (faster)</p>
            <p className="text-gray-400 text-xs">Only fetch tax-delinquent properties</p>
          </div>
        </label>
        <div>
          <label className="block text-white text-sm mb-1">Record limit</label>
          <input type="number" value={limit} onChange={e => setLimit(e.target.value)} placeholder="Leave blank for all records" className="w-full bg-gray-700 border border-gray-600 text-white placeholder-gray-500 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
          <p className="text-gray-400 text-xs mt-1">Start with 100 to test, remove limit for full ingest</p>
        </div>
        <div>
          <label className="block text-white text-sm mb-1">Cron Secret</label>
          <input type="password" value={cronSecret} onChange={e => setCronSecret(e.target.value)} placeholder="From Vercel environment variables" className="w-full bg-gray-700 border border-gray-600 text-white placeholder-gray-500 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
        </div>
      </div>
      <button onClick={runIngest} disabled={running} className={`w-full py-3 rounded-lg font-semibold text-white transition-colors ${running ? 'bg-gray-600 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-500'}`}>
        {running ? 'Running ingestion\u2026' : 'Run Ingestion'}
      </button>
      {error && (
        <div className="bg-red-900/40 border border-red-700 rounded-lg p-4 text-red-300 text-sm">
          <p className="font-semibold mb-1">Error</p><p>{error}</p>
        </div>
      )}
      {result && (
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-5 space-y-4">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-400" />
            <h2 className="text-white font-semibold">{result.status === 'dry_run' ? 'Dry Run Complete' : 'Ingestion Complete'}</h2>
            {result.elapsed_seconds && <span className="text-gray-400 text-xs ml-auto">{result.elapsed_seconds}s</span>}
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-gray-700 rounded p-3 text-center">
              <p className="text-2xl font-bold text-white">{result.fetched ?? '\u2014'}</p>
              <p className="text-gray-400 text-xs mt-1">Fetched</p>
            </div>
            <div className="bg-gray-700 rounded p-3 text-center">
              <p className="text-2xl font-bold text-white">{result.upserted ?? '\u2014'}</p>
              <p className="text-gray-400 text-xs mt-1">Upserted</p>
            </div>
            <div className="bg-gray-700 rounded p-3 text-center">
              <p className="text-2xl font-bold text-green-400">
                {typeof result.signals === 'object' && result.signals && 'processed' in result.signals ? result.signals.processed : '\u2014'}
              </p>
              <p className="text-gray-400 text-xs mt-1">Signals run</p>
            </div>
          </div>
          {result.sample && result.sample.length > 0 && (
            <div>
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-2">Sample (first 3)</p>
              <pre className="bg-gray-900 rounded p-3 text-xs text-green-300 overflow-x-auto">{JSON.stringify(result.sample.slice(0, 3), null, 2)}</pre>
            </div>
          )}
          {result.status !== 'dry_run' && (
            <a href="/leads" className="block text-center text-blue-400 hover:text-blue-300 text-sm underline">View leads \u2192</a>
          )}
        </div>
      )}
    </div>
  );
}
