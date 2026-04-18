'use client';
import { useState, useEffect, useCallback } from 'react';
import { createClient } from '@/lib/supabase';
import { useAuth } from '@/contexts/AuthContext';
import { getClientApiBaseUrl } from '@/lib/api';
import { downloadCsv } from '@/lib/exportCsv';

export interface SavedSearch {
  id: string;
  name: string;
  filters: Record<string, string>;
  created_at: string;
}

export function useSavedSearches() {
  const { user } = useAuth();
  const [searches, setSearches] = useState<SavedSearch[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!user) { setSearches([]); return; }
    setLoading(true);
    const { data } = await createClient()
      .from('saved_searches')
      .select('*')
      .order('created_at', { ascending: false });
    setSearches((data as SavedSearch[]) ?? []);
    setLoading(false);
  }, [user]);

  useEffect(() => { refresh(); }, [refresh]);

  async function save(name: string, filters: Record<string, string>) {
    if (!user) return null;
    const { data, error } = await createClient()
      .from('saved_searches')
      .insert({ user_id: user.id, name, filters })
      .select()
      .single();
    if (!error) await refresh();
    return error ? null : (data as SavedSearch);
  }

  async function remove(id: string) {
    await createClient().from('saved_searches').delete().eq('id', id);
    await refresh();
  }

  async function exportSearch(search: SavedSearch) {
    const params = new URLSearchParams({ limit: '250', ...search.filters });
    const res = await fetch(`${getClientApiBaseUrl()}/api/leads?${params}`);
    if (!res.ok) return;
    const data = await res.json();
    const leads = Array.isArray(data) ? data : (data.leads ?? []);
    downloadCsv(
      `${search.name.replace(/\s+/g, '_')}.csv`,
      leads,
      ['county', 'parcel_id', 'address', 'city', 'owner_name', 'assessed_value', 'score', 'rank', 'signal_count', 'last_updated']
    );
  }

  return { searches, loading, save, remove, exportSearch, refresh };
}
