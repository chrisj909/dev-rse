'use client';
import { useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { useSavedSearches } from '@/hooks/useSavedSearches';

interface Props {
  filters: Record<string, string>;
  activeFilterCount: number;
  onSaved?: () => void;
}

export default function SaveSearchButton({ filters, activeFilterCount, onSaved }: Props) {
  const { user } = useAuth();
  const { save } = useSavedSearches();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  if (!user) {
    return (
      <Link
        href="/auth"
        className="rounded-full border border-gray-600 px-3 py-1 text-xs font-medium text-gray-400 hover:text-white transition-colors"
        title="Sign in to save searches"
      >
        Sign in to save
      </Link>
    );
  }

  async function handleSave() {
    if (!name.trim()) return;
    setSaving(true);
    await save(name.trim(), filters);
    setSaving(false);
    setDone(true);
    setOpen(false);
    setName('');
    setTimeout(() => setDone(false), 2000);
    onSaved?.();
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        disabled={activeFilterCount === 0}
        title={activeFilterCount === 0 ? 'Apply at least one filter to save' : 'Save this search'}
        className={`rounded-full px-3 py-1 text-xs font-medium transition-colors border ${
          done
            ? 'border-green-600 bg-green-600/20 text-green-300'
            : activeFilterCount === 0
            ? 'border-gray-700 text-gray-600 cursor-not-allowed'
            : 'border-gray-600 text-gray-300 hover:border-blue-500 hover:text-white'
        }`}
      >
        {done ? '✓ Saved' : '+ Save Search'}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-8 z-50 w-64 bg-gray-800 border border-gray-700 rounded-xl shadow-xl p-4 space-y-3">
            <p className="text-white text-sm font-semibold">Save Search</p>
            <input
              type="text"
              autoFocus
              value={name}
              onChange={e => setName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSave()}
              placeholder="e.g. Shelby Rank A delinquent"
              className="w-full bg-gray-900/50 border border-gray-700 text-white placeholder-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
            />
            <div className="flex gap-2">
              <button
                onClick={handleSave}
                disabled={!name.trim() || saving}
                className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium rounded-lg py-1.5 transition-colors"
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button onClick={() => setOpen(false)} className="px-3 py-1.5 text-sm text-gray-400 hover:text-white rounded-lg border border-gray-700">
                Cancel
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
