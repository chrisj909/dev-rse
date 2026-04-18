'use client';
import { useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useSavedSearches, type SavedSearch } from '@/hooks/useSavedSearches';
import Link from 'next/link';

interface Props {
  trigger?: React.ReactNode;
}

export default function SavedSearchesModal({ trigger }: Props) {
  const { user } = useAuth();
  const { searches, loading, remove, exportSearch, refresh } = useSavedSearches();
  const [open, setOpen] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);
  const router = useRouter();
  const pathname = usePathname();

  function loadSearch(search: SavedSearch) {
    const params = new URLSearchParams(search.filters as Record<string, string>);
    router.push(`/leads?${params.toString()}`);
    setOpen(false);
  }

  async function handleExport(search: SavedSearch) {
    setExporting(search.id);
    await exportSearch(search);
    setExporting(null);
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => { if (!open) refresh(); setOpen(o => !o); }}
        className="rounded-full border border-gray-600 bg-gray-700/80 px-3 py-1 text-xs font-medium text-gray-300 transition-colors hover:border-gray-500 hover:bg-gray-700"
      >
        {trigger ?? 'Saved Searches'}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-8 z-50 w-80 bg-gray-800 border border-gray-700 rounded-xl shadow-xl overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
              <p className="text-white text-sm font-semibold">Saved Searches</p>
              <button onClick={() => setOpen(false)} className="text-gray-500 hover:text-white text-lg leading-none">×</button>
            </div>

            {!user ? (
              <div className="p-4 text-center space-y-2">
                <p className="text-gray-400 text-sm">Sign in to save and load searches.</p>
                <Link href="/auth" onClick={() => setOpen(false)} className="text-blue-400 hover:text-blue-300 text-sm underline">Sign in →</Link>
              </div>
            ) : loading ? (
              <div className="p-4 text-center text-gray-500 text-sm">Loading…</div>
            ) : searches.length === 0 ? (
              <div className="p-4 text-center text-gray-500 text-sm">No saved searches yet. Apply filters and click &ldquo;+ Save Search&rdquo;.</div>
            ) : (
              <ul className="max-h-80 overflow-y-auto divide-y divide-gray-700">
                {searches.map(s => (
                  <li key={s.id} className="px-4 py-3 hover:bg-gray-700/40 transition-colors">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-white text-sm font-medium truncate">{s.name}</p>
                        <p className="text-gray-500 text-xs mt-0.5">
                          {new Date(s.created_at).toLocaleDateString()} · {Object.keys(s.filters).filter(k => !['sort_by','sort_dir','page','page_size'].includes(k) && s.filters[k]).length} filters
                        </p>
                      </div>
                      <div className="flex-shrink-0 flex gap-1.5">
                        <button
                          onClick={() => loadSearch(s)}
                          className="text-xs text-blue-400 hover:text-blue-300 px-2 py-1 rounded border border-blue-800 hover:border-blue-600 transition-colors"
                        >
                          Load
                        </button>
                        <button
                          onClick={() => handleExport(s)}
                          disabled={exporting === s.id}
                          className="text-xs text-gray-400 hover:text-white px-2 py-1 rounded border border-gray-700 hover:border-gray-500 transition-colors disabled:opacity-50"
                        >
                          {exporting === s.id ? '…' : 'CSV'}
                        </button>
                        <button
                          onClick={() => remove(s.id)}
                          className="text-xs text-red-500 hover:text-red-400 px-2 py-1 rounded border border-gray-700 hover:border-red-800 transition-colors"
                        >
                          ×
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
