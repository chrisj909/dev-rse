'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { usePropertyLists } from '@/hooks/usePropertyLists';

interface Props {
  county: string;
  parcelId: string;
  variant?: 'button' | 'compact';
}

export default function AddToListButton({ county, parcelId, variant = 'button' }: Props) {
  const { user } = useAuth();
  const { lists, createList, addToList, removeFromList, isInAnyList, getListItems } = usePropertyLists();
  const [open, setOpen] = useState(false);
  const [inLists, setInLists] = useState<string[]>([]);
  const [newListName, setNewListName] = useState('');
  const [creating, setCreating] = useState(false);
  const [showNewInput, setShowNewInput] = useState(false);

  useEffect(() => {
    if (user) {
      isInAnyList(county, parcelId).then(setInLists);
    }
  }, [user, county, parcelId]);

  if (!user) {
    return (
      <Link href="/auth" className="text-xs text-gray-400 hover:text-blue-400 underline">
        Sign in to save
      </Link>
    );
  }

  async function toggleList(listId: string) {
    const items = await getListItems(listId);
    const item = items.find(i => i.county === county && i.parcel_id === parcelId);
    if (item) {
      await removeFromList(item.id);
      setInLists(prev => prev.filter(id => id !== listId));
    } else {
      await addToList(listId, county, parcelId);
      setInLists(prev => [...prev, listId]);
    }
  }

  async function handleCreateAndAdd() {
    if (!newListName.trim()) return;
    setCreating(true);
    const list = await createList(newListName.trim());
    if (list) {
      await addToList(list.id, county, parcelId);
      setInLists(prev => [...prev, list.id]);
    }
    setNewListName('');
    setShowNewInput(false);
    setCreating(false);
  }

  const isInAny = inLists.length > 0;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors border ${
          isInAny
            ? 'border-blue-700 bg-blue-900/30 text-blue-300 hover:bg-blue-900/50'
            : 'border-gray-700 bg-gray-800 text-gray-300 hover:border-gray-600 hover:text-white'
        }`}
      >
        <span>{isInAny ? '★' : '☆'}</span>
        <span>{isInAny ? `In ${inLists.length} list${inLists.length > 1 ? 's' : ''}` : 'Add to List'}</span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-10 z-50 w-64 bg-gray-800 border border-gray-700 rounded-xl shadow-xl overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
              <p className="text-white text-sm font-semibold">Property Lists</p>
              <button onClick={() => setOpen(false)} className="text-gray-500 hover:text-white text-lg leading-none">×</button>
            </div>

            {lists.length === 0 && !showNewInput ? (
              <div className="p-4 text-center space-y-2">
                <p className="text-gray-400 text-sm">No lists yet.</p>
                <button onClick={() => setShowNewInput(true)} className="text-blue-400 hover:text-blue-300 text-sm underline">Create your first list</button>
              </div>
            ) : (
              <ul className="max-h-48 overflow-y-auto divide-y divide-gray-700">
                {lists.map(list => (
                  <li key={list.id}>
                    <button
                      onClick={() => toggleList(list.id)}
                      className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-700/40 transition-colors text-left"
                    >
                      <span className={`text-base ${inLists.includes(list.id) ? 'text-blue-400' : 'text-gray-600'}`}>
                        {inLists.includes(list.id) ? '✓' : '○'}
                      </span>
                      <span className="text-white text-sm truncate">{list.name}</span>
                      <span className="ml-auto text-gray-500 text-xs">{list.item_count}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <div className="border-t border-gray-700 p-3">
              {showNewInput ? (
                <div className="flex gap-2">
                  <input
                    type="text"
                    autoFocus
                    value={newListName}
                    onChange={e => setNewListName(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleCreateAndAdd()}
                    placeholder="List name…"
                    className="flex-1 bg-gray-900/50 border border-gray-700 text-white placeholder-gray-600 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-blue-500"
                  />
                  <button
                    onClick={handleCreateAndAdd}
                    disabled={!newListName.trim() || creating}
                    className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg px-2.5 py-1.5"
                  >
                    {creating ? '…' : 'Add'}
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setShowNewInput(true)}
                  className="w-full text-left text-xs text-gray-400 hover:text-white transition-colors"
                >
                  + New list
                </button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
