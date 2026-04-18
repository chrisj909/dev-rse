import Link from 'next/link';
import { notFound } from 'next/navigation';

import { getServerApiBaseUrl } from '../../../lib/server-api';
import { DEFAULT_SCORING_MODE, getScoringModeLabel, normalizeScoringMode } from '../../../lib/scoringModes';

export const dynamic = 'force-dynamic';

interface LeadDetail {
  property_id: string;
  county: string;
  parcel_id: string;
  address: string | null;
  city: string | null;
  owner_name: string | null;
  mailing_address: string | null;
  assessed_value: number | null;
  state: string;
  signals: Record<string, boolean>;
  score: {
    score: number;
    rank: string;
    reason: string[];
    scoring_mode?: string;
    scoring_version?: string;
    last_updated: string;
  };
}

function formatCounty(county: string) {
  if (!county) return 'County unavailable';
  return `${county.charAt(0).toUpperCase()}${county.slice(1)} County`;
}

async function getLead(parcel_id: string, county?: string, scoringMode?: string): Promise<LeadDetail | null> {
  try {
    const baseUrl = await getServerApiBaseUrl();
    const params = new URLSearchParams();
    if (county) params.set('county', county);
    if (scoringMode && scoringMode !== DEFAULT_SCORING_MODE) params.set('scoring_mode', scoringMode);
    const query = params.toString();
    const res = await fetch(`${baseUrl}/api/leads/${encodeURIComponent(parcel_id)}${query ? `?${query}` : ''}`, { cache: 'no-store' });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}

const SIGNAL_DESCRIPTIONS: Record<string, string> = {
  absentee_owner: 'Owner mailing address differs from property address — likely a non-resident landlord or investor.',
  long_term_owner: 'Property has been held by the same owner for 10+ years — potential motivation to sell.',
  out_of_state_owner: 'Owner mails to an address outside Alabama — absentee investor.',
  corporate_owner: 'Owner name resembles an LLC, trust, or other corporate entity.',
  tax_delinquent: 'Property has unpaid property taxes — financial pressure on the owner.',
  pre_foreclosure: 'A lis pendens or notice of default has been filed against this property.',
  probate: 'Property is linked to a probate estate filing — heir-owned.',
  eviction: 'An eviction filing has been recorded against this property.',
  code_violation: 'An open code violation or nuisance complaint is on record.',
};

const SCORE_DRIVER_DESCRIPTIONS: Record<string, string> = {
  absentee_owner: 'Absentee ownership contributes to score under this lens.',
  long_term_owner: 'Long hold period contributes to score — more likely motivated to sell.',
  out_of_state_owner: 'Out-of-state ownership is weighted for this scoring mode.',
  corporate_owner: 'Corporate/entity ownership contributes to score.',
  tax_delinquent: 'Tax delinquency is a high-weight distress signal.',
  pre_foreclosure: 'Pre-foreclosure filing is a high-weight distress signal.',
  probate: 'Probate status contributes to distress scoring.',
  eviction: 'Active eviction filing contributes to distress scoring.',
  code_violation: 'Open code violation contributes to distress scoring.',
  distress_combo: 'Bonus applied when multiple distress signals are present simultaneously.',
};

function sourceUrl(county: string, parcelId: string): string | null {
  if (county === 'shelby') {
    return `https://maps.shelbyal.com/gisserver/rest/services`;
  }
  if (county === 'jefferson') {
    return `https://jccgis.jccal.org/server/rest/services/Basemap/Parcels/MapServer/0/query?where=OBJECTID+IS+NOT+NULL&outFields=*&f=html`;
  }
  return null;
}

function RankBadge({ rank }: { rank: string }) {
  const colors: Record<string, string> = {
    A: 'bg-green-600 text-white',
    B: 'bg-yellow-500 text-black',
    C: 'bg-gray-500 text-white',
  };
  return (
    <span className={`px-3 py-1 rounded text-sm font-bold ${colors[rank] ?? 'bg-gray-600 text-white'}`}>
      Rank {rank}
    </span>
  );
}

export default async function PropertyDetail({
  params,
  searchParams,
}: {
  params: Promise<{ parcel_id: string }>;
  searchParams: Promise<{ county?: string; scoring_mode?: string }>;
}) {
  const { parcel_id } = await params;
  const { county, scoring_mode } = await searchParams;
  const scoringMode = normalizeScoringMode(scoring_mode);
  const lead = await getLead(parcel_id, county, scoringMode);
  if (!lead) notFound();
  const activeSignals = Object.entries(lead.signals).filter(([, isActive]) => Boolean(isActive));
  const scoreDrivers = lead.score.reason.filter(reason => reason !== 'distress_combo');
  const hasDistressBonus = lead.score.reason.includes('distress_combo');

  return (
    <div className="p-6 max-w-2xl space-y-6">
      <div>
        <Link href={scoringMode === DEFAULT_SCORING_MODE ? '/leads' : `/leads?scoring_mode=${encodeURIComponent(scoringMode)}`} className="text-blue-400 hover:text-blue-300 text-sm">← Back to Leads</Link>
      </div>

      <div>
        <h1 className="text-2xl font-bold text-slate-900">{lead.address || 'Address unavailable'}</h1>
        <p className="text-slate-500 mt-1">{[lead.city, formatCounty(lead.county), lead.state].filter(Boolean).join(', ') || 'Location unavailable'}</p>
      </div>

      <div className="bg-gray-800 rounded-lg border border-gray-700 divide-y divide-gray-700">
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">Owner</span>
          <span className="text-white font-medium">{lead.owner_name ?? '—'}</span>
        </div>
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">County</span>
          <span className="text-white font-medium">{formatCounty(lead.county)}</span>
        </div>
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">Parcel ID</span>
          <span className="text-white font-mono text-sm">{lead.parcel_id}</span>
        </div>
        <div className="flex justify-between items-center px-5 py-4">
          <span className="text-gray-400">Score</span>
          <span className="text-white text-xl font-bold font-mono">{lead.score.score}</span>
        </div>
        <div className="flex justify-between items-center px-5 py-4">
          <span className="text-gray-400">Rank</span>
          <RankBadge rank={lead.score.rank} />
        </div>
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">Signals Detected</span>
          <span className="text-white font-medium">{activeSignals.length}</span>
        </div>
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">Scoring Mode</span>
          <span className="text-white font-medium">{getScoringModeLabel(lead.score.scoring_mode ?? scoringMode)}</span>
        </div>
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">Scoring Version</span>
          <span className="text-white font-medium">{lead.score.scoring_version ?? 'v3'}</span>
        </div>
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">Mailing Address</span>
          <span className="text-white font-medium">{lead.mailing_address ?? '—'}</span>
        </div>
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">Assessed Value</span>
          <span className="text-white font-medium">{lead.assessed_value != null ? `$${lead.assessed_value.toLocaleString()}` : '—'}</span>
        </div>
        <div className="flex justify-between px-5 py-4">
          <span className="text-gray-400">Last Updated</span>
          <span className="text-gray-300 text-sm">
            {lead.score.last_updated ? new Date(lead.score.last_updated).toLocaleString() : '—'}
          </span>
        </div>
      </div>

      <div className="bg-gray-800 rounded-lg border border-gray-700 p-5 space-y-3">
        <h2 className="text-white font-semibold text-sm uppercase tracking-wide">Active Signals</h2>
        {activeSignals.length === 0 ? (
          <p className="text-gray-400 text-sm">No active signals on this property.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {activeSignals.map(([signalName]) => (
              <span
                key={signalName}
                title={SIGNAL_DESCRIPTIONS[signalName] ?? signalName}
                className="rounded-full bg-blue-600/20 px-3 py-1 text-sm text-blue-200 cursor-help"
              >
                {signalName.replaceAll('_', ' ')}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="bg-gray-800 rounded-lg border border-gray-700 p-5 space-y-3">
        <h2 className="text-white font-semibold text-sm uppercase tracking-wide">Score Drivers</h2>
        {scoreDrivers.length === 0 && !hasDistressBonus ? (
          <p className="text-gray-400 text-sm">No active scoring drivers on this property.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {scoreDrivers.map(reason => (
              <span
                key={reason}
                title={SCORE_DRIVER_DESCRIPTIONS[reason] ?? reason}
                className="rounded-full bg-emerald-600/15 px-3 py-1 text-sm text-emerald-200 cursor-help"
              >
                {reason.replaceAll('_', ' ')}
              </span>
            ))}
            {hasDistressBonus ? (
              <span
                title={SCORE_DRIVER_DESCRIPTIONS['distress_combo']}
                className="rounded-full bg-amber-500/15 px-3 py-1 text-sm text-amber-200 cursor-help"
              >
                distress combo bonus
              </span>
            ) : null}
          </div>
        )}
      </div>

      {sourceUrl(lead.county, lead.parcel_id) && (
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-5">
          <h2 className="text-white font-semibold text-sm uppercase tracking-wide mb-3">Source Data</h2>
          <a
            href={sourceUrl(lead.county, lead.parcel_id)!}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:text-blue-300 text-sm underline"
          >
            {lead.county === 'shelby' ? 'Shelby County GIS Portal' : 'Jefferson County GIS Portal'} →
          </a>
        </div>
      )}
    </div>
  );
}
