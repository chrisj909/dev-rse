'use client';
import { useState, useEffect, useCallback } from 'react';

import { getClientApiBaseUrl } from '../../lib/api';

interface IngestResult {
  status: string;
  county?: string;
  fetched?: number;
  upserted?: number;
  batches_completed?: number;
  signals?: { processed?: number; error?: string };
  scoring?: { processed?: number; errors?: number; error?: string };
  tax_delinquency?: { processed?: number; updated?: number; not_found?: number };
  retrieval?: {
    mode?: string;
    updated_since?: string | null;
    delta_days?: number | null;
    start_offset?: number;
    next_offset?: number | null;
    has_more?: boolean;
  };
  elapsed_seconds?: number;
  sample?: unknown[];
  error?: string;
}

interface DbStats {
  properties: number;
  signals: number;
  scores: Record<string, number>;
}

const DEFAULT_BATCH_SIZE = 250;

function summarizeErrorText(status: number, text: string): string {
  const trimmed = text.trim();
  if (!trimmed) {
    return `HTTP ${status}`;
  }

  if (trimmed.includes('Authentication Required')) {
    return 'Request was blocked by deployment protection before it reached the API.';
  }

  if (trimmed.startsWith('An error occurred')) {
    return `${trimmed} This usually means the serverless function failed before returning JSON.`;
  }

  const normalized = trimmed
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  return normalized ? `HTTP ${status}: ${normalized.slice(0, 240)}` : `HTTP ${status}`;
}

async function readApiResponse(res: Response): Promise<{ json: unknown | null; text: string }> {
  const text = await res.text();
  if (!text.trim()) {
    return { json: null, text };
  }

  try {
    return { json: JSON.parse(text), text };
  } catch {
    return { json: null, text };
  }
}

export default function IngestPage() {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<IngestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [dryRun, setDryRun] = useState(true);
  const [delinquentOnly, setDelinquentOnly] = useState(false);
  const [county, setCounty] = useState('all');
  const [limit, setLimit] = useState('100');
  const [cronSecret, setCronSecret] = useState('');
  const [rescoring, setRescoring] = useState(false);
  const [rescoreProgress, setRescoreProgress] = useState<string | null>(null);
  const [rescoreError, setRescoreError] = useState<string | null>(null);
  const [dbStats, setDbStats] = useState<DbStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${getClientApiBaseUrl()}/api/health/stats`);
      if (res.ok) setDbStats(await res.json());
    } catch { /* non-critical */ } finally {
      setStatsLoading(false);
    }
  }, []);

  useEffect(() => { fetchStats(); }, [fetchStats]);

  async function requestIngest(params: URLSearchParams): Promise<IngestResult> {
    const res = await fetch(`${getClientApiBaseUrl()}/api/ingest/run?${params}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(cronSecret ? { 'x-cron-secret': cronSecret } : {}),
      },
    });
    const { json, text } = await readApiResponse(res);

    if (!res.ok) {
      if (json && typeof json === 'object' && json !== null) {
        const detail = 'detail' in json ? json.detail : null;
        const message = 'message' in json ? json.message : null;
        if (typeof detail === 'string' && detail.trim()) {
          throw new Error(detail);
        }
        if (typeof message === 'string' && message.trim()) {
          throw new Error(message);
        }
        throw new Error(JSON.stringify(json));
      }
      throw new Error(summarizeErrorText(res.status, text));
    }

    if (json && typeof json === 'object') {
      return json as IngestResult;
    }

    throw new Error('The API returned a non-JSON success response, so the ingest result could not be displayed.');
  }

  async function runIngest() {
    setRunning(true);
    setResult(null);
    setError(null);
    setProgress(null);
    try {
      const trimmedLimit = limit.trim();
      const autoBatch = !dryRun && !delinquentOnly && county !== 'all' && !trimmedLimit;

      if (!trimmedLimit && county === 'all' && !dryRun) {
        throw new Error('Full all-county ingest is too large for one serverless request. Select a single county or enter a record limit.');
      }

      if (autoBatch) {
        let startOffset = 0;
        let batchNumber = 0;
        const aggregate: IngestResult = {
          status: 'ok',
          county,
          fetched: 0,
          upserted: 0,
          batches_completed: 0,
          signals: { processed: 0 },
          scoring: { processed: 0, errors: 0 },
          tax_delinquency: { processed: 0, updated: 0, not_found: 0 },
          retrieval: { mode: 'full', start_offset: 0, next_offset: null, has_more: false },
          elapsed_seconds: 0,
        };

        while (true) {
          batchNumber += 1;
          setProgress(`Running batch ${batchNumber} from offset ${startOffset}...`);

          const params = new URLSearchParams();
          params.set('county', county);
          params.set('limit', String(DEFAULT_BATCH_SIZE));
          params.set('start_offset', String(startOffset));

          const batch = await requestIngest(params);
          aggregate.fetched = (aggregate.fetched ?? 0) + (batch.fetched ?? 0);
          aggregate.upserted = (aggregate.upserted ?? 0) + (batch.upserted ?? 0);
          aggregate.batches_completed = batchNumber;
          aggregate.elapsed_seconds = (aggregate.elapsed_seconds ?? 0) + (batch.elapsed_seconds ?? 0);

          if (aggregate.signals && batch.signals?.processed) {
            aggregate.signals.processed = (aggregate.signals.processed ?? 0) + batch.signals.processed;
          }
          if (aggregate.scoring) {
            aggregate.scoring.processed = (aggregate.scoring.processed ?? 0) + (batch.scoring?.processed ?? 0);
            aggregate.scoring.errors = (aggregate.scoring.errors ?? 0) + (batch.scoring?.errors ?? 0);
          }
          if (aggregate.tax_delinquency) {
            aggregate.tax_delinquency.processed = (aggregate.tax_delinquency.processed ?? 0) + (batch.tax_delinquency?.processed ?? 0);
            aggregate.tax_delinquency.updated = (aggregate.tax_delinquency.updated ?? 0) + (batch.tax_delinquency?.updated ?? 0);
            aggregate.tax_delinquency.not_found = (aggregate.tax_delinquency.not_found ?? 0) + (batch.tax_delinquency?.not_found ?? 0);
          }

          aggregate.retrieval = batch.retrieval ?? aggregate.retrieval;

          const nextOffset = batch.retrieval?.next_offset;
          const hasMore = batch.retrieval?.has_more === true;
          if (!hasMore || batch.fetched === 0 || nextOffset == null || nextOffset <= startOffset) {
            aggregate.retrieval = {
              ...(aggregate.retrieval ?? {}),
              start_offset: 0,
              next_offset: null,
              has_more: false,
            };
            setResult(aggregate);
            setProgress(`Completed ${batchNumber} batch${batchNumber === 1 ? '' : 'es'}.`);
            break;
          }

          startOffset = nextOffset;
          setProgress(`Completed batch ${batchNumber}; ${aggregate.fetched} records fetched so far.`);
        }
      } else {
        const params = new URLSearchParams();
        if (county) params.set('county', county);
        if (dryRun) params.set('dry_run', 'true');
        if (delinquentOnly) params.set('delinquent_only', 'true');
        if (trimmedLimit) params.set('limit', trimmedLimit);

        const singleRun = await requestIngest(params);
        setResult(singleRun);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Network error');
    } finally {
      setRunning(false);
      fetchStats();
    }
  }

  async function runRescore() {
    if (!cronSecret) {
      setRescoreError('Cron Secret is required to run a rescore.');
      return;
    }
    setRescoring(true);
    setRescoreProgress(null);
    setRescoreError(null);
    try {
      let offset = 0;
      let batch = 0;
      let total = 0;
      while (true) {
        batch += 1;
        const params = new URLSearchParams({ offset: String(offset), limit: '500' });
        const res = await fetch(
          `${getClientApiBaseUrl()}/api/cron/run-signals?${params}`,
          { headers: { 'x-cron-secret': cronSecret } },
        );
        if (!res.ok) {
          const text = await res.text();
          throw new Error(summarizeErrorText(res.status, text));
        }
        const data = await res.json() as {
          status?: string; error?: string;
          has_more: boolean; next_offset: number;
          total_properties: number; processed: number;
        };
        if (data.status === 'error') {
          throw new Error(data.error ?? 'Unknown error from cron endpoint');
        }
        total = data.total_properties;
        offset = data.next_offset;
        setRescoreProgress(`Batch ${batch} — scored ${offset} / ${total} properties`);
        if (!data.has_more || data.processed === 0) break;
      }
      setRescoreProgress(`Done — ${offset} / ${total} properties rescored across ${batch} batches.`);
    } catch (e: unknown) {
      setRescoreError(e instanceof Error ? e.message : 'Network error');
    } finally {
      setRescoring(false);
      fetchStats();
    }
  }

  return (
    <div className="p-4 sm:p-6 max-w-2xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Data Ingestion</h1>
        <p className="text-slate-500 text-sm mt-1">Pull Shelby and Jefferson County property data and score leads</p>
      </div>

      {/* Active Sources */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-5 space-y-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-gray-400">Active Sources</p>
        {[
          { color: 'bg-green-400', name: 'Shelby County ArcGIS', detail: '106,000+ parcels · owner, address, tax status, deed date' },
          { color: 'bg-cyan-400', name: 'Jefferson County ArcGIS', detail: 'Public parcel map service · owner, mailing, address, assessed value' },
          { color: 'bg-yellow-400', name: 'GovEase Tax Lien Auction', detail: 'Shelby overlay only; Jefferson feed not publicly exposed' },
        ].map(s => (
          <div key={s.name} className="flex items-center gap-3">
            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${s.color}`} />
            <div>
              <p className="text-white text-sm font-medium">{s.name}</p>
              <p className="text-gray-500 text-xs">{s.detail}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Options */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-5 space-y-4">
        <p className="text-xs font-semibold uppercase tracking-widest text-gray-400">Options</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="flex items-center gap-3 cursor-pointer rounded-lg border border-gray-700 bg-gray-900/50 px-4 py-3 hover:border-gray-600 transition-colors">
            <input type="checkbox" checked={dryRun} onChange={e => setDryRun(e.target.checked)} className="w-4 h-4 rounded accent-blue-500 flex-shrink-0" />
            <div>
              <p className="text-white text-sm font-medium">Dry run</p>
              <p className="text-gray-500 text-xs">Preview only, no DB writes</p>
            </div>
          </label>
          <label className="flex items-center gap-3 cursor-pointer rounded-lg border border-gray-700 bg-gray-900/50 px-4 py-3 hover:border-gray-600 transition-colors">
            <input type="checkbox" checked={delinquentOnly} onChange={e => setDelinquentOnly(e.target.checked)} className="w-4 h-4 rounded accent-blue-500 flex-shrink-0" />
            <div>
              <p className="text-white text-sm font-medium">Delinquent only</p>
              <p className="text-gray-500 text-xs">Faster · tax-delinquent parcels only</p>
            </div>
          </label>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5 uppercase tracking-wide">County Scope</label>
            <select value={county} onChange={e => setCounty(e.target.value)} className="w-full bg-gray-900/50 border border-gray-700 text-white rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors">
              <option value="all">All supported counties</option>
              <option value="shelby">Shelby County</option>
              <option value="jefferson">Jefferson County</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5 uppercase tracking-wide">Record Limit</label>
            <input type="number" value={limit} onChange={e => setLimit(e.target.value)} placeholder="All records (auto-batch)" className="w-full bg-gray-900/50 border border-gray-700 text-white placeholder-gray-600 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors" />
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1.5 uppercase tracking-wide">Cron Secret</label>
          <input type="password" value={cronSecret} onChange={e => setCronSecret(e.target.value)} placeholder="From Vercel environment variables" className="w-full bg-gray-900/50 border border-gray-700 text-white placeholder-gray-600 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors" />
          <p className="text-gray-600 text-xs mt-1.5">Required for live writes and rescore. Start with limit 100 to test.</p>
        </div>
      </div>

      {/* Run button */}
      <button
        onClick={runIngest}
        disabled={running}
        className={`w-full py-3 rounded-xl font-semibold text-white transition-all flex items-center justify-center gap-2 ${
          running ? 'bg-blue-700/70 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-500 active:scale-[0.99]'
        }`}
      >
        {running && <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
        {running ? 'Running ingestion\u2026' : 'Run Ingestion'}
      </button>

      {/* Progress */}
      {progress && (
        <div className="bg-gray-800 border border-gray-700 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-1">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
            <p className="text-gray-300 text-xs font-semibold uppercase tracking-wide">In Progress</p>
          </div>
          <p className="text-gray-400 text-sm">{progress}</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-gray-800 border border-red-800 rounded-xl p-4">
          <p className="text-red-400 text-xs font-semibold uppercase tracking-wide mb-1">Error</p>
          <p className="text-red-300 text-sm">{error}</p>
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="bg-gray-800 rounded-xl border border-gray-700 p-5 space-y-4">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="w-2 h-2 rounded-full bg-green-400" />
            <h2 className="text-white font-semibold">{result.status === 'dry_run' ? 'Dry Run Complete' : 'Ingestion Complete'}</h2>
            {result.county && <span className="rounded-full bg-gray-700 px-2 py-0.5 text-gray-400 text-xs">{result.county}</span>}
            {result.batches_completed ? <span className="rounded-full bg-gray-700 px-2 py-0.5 text-gray-400 text-xs">{result.batches_completed} batches</span> : null}
            {result.elapsed_seconds && <span className="ml-auto text-gray-500 text-xs">{result.elapsed_seconds}s</span>}
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: 'Fetched', value: result.fetched, color: 'text-white' },
              { label: 'Upserted', value: result.upserted, color: 'text-white' },
              { label: 'Signals', value: typeof result.signals === 'object' && result.signals && 'processed' in result.signals ? result.signals.processed : undefined, color: 'text-green-400' },
              { label: 'Scored', value: typeof result.scoring === 'object' && result.scoring && 'processed' in result.scoring ? result.scoring.processed : undefined, color: 'text-blue-400' },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-gray-700/60 rounded-lg p-3 text-center">
                <p className={`text-2xl font-bold font-mono ${color}`}>{value ?? '\u2014'}</p>
                <p className="text-gray-500 text-xs mt-1">{label}</p>
              </div>
            ))}
          </div>
          {(typeof result.signals === 'object' && result.signals && 'error' in result.signals) && (
            <div className="border border-red-800 rounded-lg p-3 text-red-300 text-xs">
              <span className="font-semibold">Signal error: </span>{String(result.signals.error)}
            </div>
          )}
          {(typeof result.scoring === 'object' && result.scoring && 'error' in result.scoring) && (
            <div className="border border-red-800 rounded-lg p-3 text-red-300 text-xs">
              <span className="font-semibold">Scoring error: </span>{String((result.scoring as Record<string, unknown>).error)}
            </div>
          )}
          {result.sample && result.sample.length > 0 && (
            <div>
              <p className="text-gray-500 text-xs uppercase tracking-wide mb-2">Sample (first 3)</p>
              <pre className="bg-gray-900 rounded-lg p-3 text-xs text-green-300 overflow-x-auto">{JSON.stringify(result.sample.slice(0, 3), null, 2)}</pre>
            </div>
          )}
          {result.status !== 'dry_run' && (
            <a href="/leads" className="block text-center text-blue-400 hover:text-blue-300 text-sm">View leads →</a>
          )}
        </div>
      )}

      {/* Full Rescore */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-5 space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-gray-400">Rescore Existing Properties</p>
            <p className="text-gray-500 text-xs mt-1">Re-run signal detection and scoring without re-scraping ArcGIS. Requires Cron Secret.</p>
          </div>
          <button
            onClick={runRescore}
            disabled={rescoring || running}
            className={`flex-shrink-0 flex items-center gap-2 px-4 py-2 rounded-lg font-semibold text-sm text-white transition-all ${
              rescoring || running ? 'bg-indigo-700/50 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-500 active:scale-[0.99]'
            }`}
          >
            {rescoring && <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
            {rescoring ? 'Rescoring\u2026' : 'Run Rescore'}
          </button>
        </div>
        {rescoreProgress && (
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
            <p className="text-indigo-300 text-xs">{rescoreProgress}</p>
          </div>
        )}
        {rescoreError && (
          <p className="text-red-400 text-xs">{rescoreError}</p>
        )}
      </div>

      {/* DB Status */}
      <div className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-xs text-gray-400">
        <div className="flex items-center justify-between mb-2">
          <span className="font-semibold text-gray-300 uppercase tracking-wide text-xs">Database</span>
          <button onClick={fetchStats} className="text-blue-400 hover:text-blue-300">↻</button>
        </div>
        {statsLoading ? (
          <span className="text-gray-500">loading…</span>
        ) : dbStats ? (
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <span><span className="text-white font-medium">{dbStats.properties.toLocaleString()}</span> properties</span>
            <span><span className="text-white font-medium">{dbStats.signals.toLocaleString()}</span> signals</span>
            {Object.entries(dbStats.scores).map(([mode, count]) => {
              const label = mode === 'owner_occupant' ? 'Owner' : mode === 'investor' ? 'Investor' : 'Broad';
              return <span key={mode}><span className="text-white font-medium">{(count as number).toLocaleString()}</span> {label} scores</span>;
            })}
          </div>
        ) : (
          <span className="text-gray-500">unavailable</span>
        )}
      </div>
    </div>
  );
}
