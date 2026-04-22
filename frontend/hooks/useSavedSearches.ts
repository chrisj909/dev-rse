'use client';
import { useState, useEffect, useCallback } from 'react';
import { createClient } from '@/lib/supabase';
import { useAuth } from '@/contexts/AuthContext';
import { getClientApiBaseUrl } from '@/lib/api';
import { exportLeadResultsToCsv } from '@/lib/leadExport';

export interface SavedSearch {
  id: string;
  name: string;
  filters: Record<string, string>;
  created_at: string;
}

function sanitizeSavedSearchFilters(filters: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(filters).filter(([key, value]) => key !== 'scoring_mode' && Boolean(value)),
  );
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
    const sanitizedFilters = sanitizeSavedSearchFilters(filters);
    const { data, error } = await createClient()
      .from('saved_searches')
      .insert({ user_id: user.id, name, filters: sanitizedFilters })
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
    await exportLeadResultsToCsv(
      `${search.name.replace(/\s+/g, '_')}.csv`,
      {
        baseUrl: getClientApiBaseUrl(),
        filters: sanitizeSavedSearchFilters(search.filters),
      },
    );
  }

  return { searches, loading, save, remove, exportSearch, refresh };
}
