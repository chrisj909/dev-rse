'use client';
import { useState } from 'react';

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

const DEFAULT_BATCH_SIZE = 1000;

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
    }
  }

  return (
    <div className="p-6 max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Data Ingestion</h1>
        <p className="text-slate-500 text-sm mt-1">Pull Shelby and Jefferson County property data and score leads</p>
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
          <span className="w-2 h-2 rounded-full bg-cyan-400" />
          <div>
            <p className="text-white text-sm font-medium">Jefferson County ArcGIS</p>
            <p className="text-gray-400 text-xs">Public parcel map service · owner, mailing, address, assessed value</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="w-2 h-2 rounded-full bg-yellow-400" />
          <div>
            <p className="text-white text-sm font-medium">GovEase Tax Lien Auction</p>
            <p className="text-gray-400 text-xs">Shelby overlay only at the moment; Jefferson feed not publicly exposed there</p>
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
            <p className="text-gray-400 text-xs">Only fetch tax-delinquent properties from sources that publish delinquency fields</p>
          </div>
        </label>
        <div>
          <label className="block text-white text-sm mb-1">County Scope</label>
          <select value={county} onChange={e => setCounty(e.target.value)} className="w-full bg-gray-700 border border-gray-600 text-white rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500">
            <option value="all">All supported counties</option>
            <option value="shelby">Shelby County</option>
            <option value="jefferson">Jefferson County</option>
          </select>
          <p className="text-gray-400 text-xs mt-1">Use Jefferson for parcel expansion research or all counties for a combined ingest.</p>
        </div>
        <div>
          <label className="block text-white text-sm mb-1">Record limit</label>
          <input type="number" value={limit} onChange={e => setLimit(e.target.value)} placeholder="Leave blank for all records" className="w-full bg-gray-700 border border-gray-600 text-white placeholder-gray-500 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
          <p className="text-gray-400 text-xs mt-1">Start with 100 to test. Leave blank on a single-county live ingest to auto-batch the full run in 1,000-record chunks.</p>
        </div>
        <div>
          <label className="block text-white text-sm mb-1">Cron Secret</label>
          <input type="password" value={cronSecret} onChange={e => setCronSecret(e.target.value)} placeholder="From Vercel environment variables" className="w-full bg-gray-700 border border-gray-600 text-white placeholder-gray-500 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
        </div>
      </div>
      <button onClick={runIngest} disabled={running} className={`w-full py-3 rounded-lg font-semibold text-white transition-colors ${running ? 'bg-gray-600 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-500'}`}>
        {running ? 'Running ingestion\u2026' : 'Run Ingestion'}
      </button>
      {progress && (
        <div className="bg-blue-900/30 border border-blue-700 rounded-lg p-4 text-blue-200 text-sm">
          <p className="font-semibold mb-1">Progress</p>
          <p>{progress}</p>
        </div>
      )}
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
            {result.county && <span className="text-gray-400 text-xs">scope: {result.county}</span>}
            {result.batches_completed ? <span className="text-gray-400 text-xs">batches: {result.batches_completed}</span> : null}
            {result.elapsed_seconds && <span className="text-gray-400 text-xs ml-auto">{result.elapsed_seconds}s</span>}
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
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
            <div className="bg-gray-700 rounded p-3 text-center">
              <p className="text-2xl font-bold text-blue-400">
                {typeof result.scoring === 'object' && result.scoring && 'processed' in result.scoring ? result.scoring.processed : '\u2014'}
              </p>
              <p className="text-gray-400 text-xs mt-1">Scored</p>
            </div>
          </div>
          {(typeof result.signals === 'object' && result.signals && 'error' in result.signals) && (
            <div className="bg-red-900/30 border border-red-700 rounded p-3 text-red-300 text-xs">
              <span className="font-semibold">Signal error: </span>{String(result.signals.error)}
            </div>
          )}
          {(typeof result.scoring === 'object' && result.scoring && 'error' in result.scoring) && (
            <div className="bg-red-900/30 border border-red-700 rounded p-3 text-red-300 text-xs">
              <span className="font-semibold">Scoring error: </span>{String((result.scoring as Record<string, unknown>).error)}
            </div>
          )}
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
