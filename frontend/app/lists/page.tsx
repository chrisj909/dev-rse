'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { usePropertyLists, type PropertyList, type PropertyListItem } from '@/hooks/usePropertyLists';

function RankBadge({ rank }: { rank?: string }) {
  if (!rank) return null;
  const colors: Record<string, string> = {
    A: 'bg-green-600 text-white',
    B: 'bg-yellow-500 text-black',
    C: 'bg-gray-500 text-white',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-bold ${colors[rank] ?? 'bg-gray-600 text-white'}`}>
      {rank}
    </span>
  );
}

function ListDetail({ list, onClose }: { list: PropertyList; onClose: () => void }) {
  const { getListItems, removeFromList, exportList, deleteList } = usePropertyLists();
  const [items, setItems] = useState<PropertyListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const router = useRouter();

  useEffect(() => {
    getListItems(list.id).then(data => { setItems(data); setLoading(false); });
  }, [list.id]);

  async function handleRemove(itemId: string) {
    await removeFromList(itemId);
    setItems(prev => prev.filter(i => i.id !== itemId));
  }

  async function handleExport() {
    setExporting(true);
    await exportList(list.id, list.name);
    setExporting(false);
  }

  async function handleDelete() {
    if (!confirm(`Delete list "${list.name}"? This cannot be undone.`)) return;
    await deleteList(list.id);
    onClose();
  }

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700">
        <div>
          <h2 className="text-white font-semibold">{list.name}</h2>
          <p className="text-gray-400 text-xs mt-0.5">{items.length} properties</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleExport}
            disabled={exporting || items.length === 0}
            className="text-xs text-gray-300 hover:text-white px-3 py-1.5 rounded-lg border border-gray-700 hover:border-gray-500 transition-colors disabled:opacity-40"
          >
            {exporting ? 'Exporting…' : 'Export CSV'}
          </button>
          <button
            onClick={handleDelete}
            className="text-xs text-red-500 hover:text-red-400 px-3 py-1.5 rounded-lg border border-gray-700 hover:border-red-800 transition-colors"
          >
            Delete List
          </button>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-lg leading-none ml-1">×</button>
        </div>
      </div>

      {loading ? (
        <div className="p-8 text-center text-gray-500 text-sm">Loading…</div>
      ) : items.length === 0 ? (
        <div className="p-8 text-center text-gray-500 text-sm">No properties in this list yet.</div>
      ) : (
        <div className="divide-y divide-gray-700">
          {items.map(item => (
            <div key={item.id} className="flex items-center gap-3 px-5 py-3 hover:bg-gray-700/30 transition-colors group">
              <div
                className="flex-1 min-w-0 cursor-pointer"
                onClick={() => router.push(`/property?parcel_id=${encodeURIComponent(item.parcel_id)}&county=${encodeURIComponent(item.county)}`)}
              >
                <p className="text-white text-sm font-medium truncate hover:text-blue-300 transition-colors">
                  {item.address || 'Address unavailable'}
                </p>
                <p className="text-gray-400 text-xs mt-0.5">
                  {[item.city, item.county ? `${item.county.charAt(0).toUpperCase()}${item.county.slice(1)} County` : null].filter(Boolean).join(' · ')}
                  {item.owner_name && ` · ${item.owner_name}`}
                </p>
              </div>
              <div className="flex-shrink-0 flex items-center gap-2">
                {item.score != null && <span className="text-white font-mono text-sm">{item.score}</span>}
                <RankBadge rank={item.rank} />
                <button
                  onClick={() => handleRemove(item.id)}
                  className="text-gray-600 hover:text-red-400 text-sm opacity-0 group-hover:opacity-100 transition-all ml-1"
                  title="Remove from list"
                >
                  ×
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ListsPage() {
  const { user, loading: authLoading } = useAuth();
  const { lists, loading, createList, refresh } = usePropertyLists();
  const [selectedList, setSelectedList] = useState<PropertyList | null>(null);
  const [newListName, setNewListName] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => { refresh(); }, [refresh]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newListName.trim()) return;
    setCreating(true);
    const list = await createList(newListName.trim());
    setNewListName('');
    setCreating(false);
    if (list) setSelectedList(list as PropertyList);
  }

  if (authLoading) return null;

  if (!user) {
    return (
      <div className="p-4 sm:p-6 max-w-2xl">
        <h1 className="text-2xl font-bold text-slate-900 mb-2">Property Lists</h1>
        <p className="text-slate-500 text-sm mb-6">Save and organize properties into named lists for follow-up.</p>
        <div className="bg-gray-800 rounded-xl border border-gray-700 p-6 text-center space-y-3">
          <p className="text-gray-300">Sign in to create and manage property lists.</p>
          <Link href="/auth" className="inline-block bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg px-5 py-2.5 transition-colors">
            Sign In
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 sm:p-6 max-w-2xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Property Lists</h1>
          <p className="text-slate-500 text-sm mt-1">{lists.length} list{lists.length !== 1 ? 's' : ''}</p>
        </div>
      </div>

      {/* Create new list */}
      <form onSubmit={handleCreate} className="flex gap-2">
        <input
          type="text"
          value={newListName}
          onChange={e => setNewListName(e.target.value)}
          placeholder="New list name…"
          className="flex-1 bg-gray-800 border border-gray-700 text-white placeholder-gray-500 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 transition-colors"
        />
        <button
          type="submit"
          disabled={!newListName.trim() || creating}
          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium rounded-lg px-4 py-2 transition-colors"
        >
          {creating ? 'Creating…' : 'New List'}
        </button>
      </form>

      {/* Selected list detail */}
      {selectedList && (
        <ListDetail
          list={selectedList}
          onClose={() => { setSelectedList(null); refresh(); }}
        />
      )}

      {/* List index */}
      {loading ? (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => <div key={i} className="h-16 bg-gray-800 rounded-xl animate-pulse" />)}
        </div>
      ) : lists.length === 0 ? (
        <div className="bg-gray-800 rounded-xl border border-gray-700 p-8 text-center text-gray-500 text-sm">
          No lists yet. Create one above, then add properties from the lead feed or property detail pages.
        </div>
      ) : (
        <div className="space-y-2">
          {lists.map(list => (
            <div
              key={list.id}
              onClick={() => setSelectedList(selectedList?.id === list.id ? null : list)}
              className={`flex items-center gap-4 px-5 py-4 rounded-xl border cursor-pointer transition-colors ${
                selectedList?.id === list.id
                  ? 'bg-gray-700 border-blue-700'
                  : 'bg-gray-800 border-gray-700 hover:bg-gray-700/50'
              }`}
            >
              <div className="flex-1 min-w-0">
                <p className="text-white font-medium text-sm">{list.name}</p>
                <p className="text-gray-400 text-xs mt-0.5">
                  {list.item_count} propert{list.item_count !== 1 ? 'ies' : 'y'} · Created {new Date(list.created_at).toLocaleDateString()}
                </p>
              </div>
              <span className="text-gray-500 text-sm">{selectedList?.id === list.id ? '▲' : '▼'}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
