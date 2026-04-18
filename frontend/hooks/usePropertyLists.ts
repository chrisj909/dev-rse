'use client';
import { useState, useEffect, useCallback } from 'react';
import { createClient } from '@/lib/supabase';
import { useAuth } from '@/contexts/AuthContext';
import { downloadCsv } from '@/lib/exportCsv';

export interface PropertyList {
  id: string;
  name: string;
  created_at: string;
  item_count: number;
}

export interface PropertyListItem {
  id: string;
  list_id: string;
  county: string;
  parcel_id: string;
  added_at: string;
  // joined from properties
  address?: string | null;
  city?: string | null;
  owner_name?: string | null;
  assessed_value?: number | null;
  score?: number;
  rank?: string;
}

export function usePropertyLists() {
  const { user } = useAuth();
  const [lists, setLists] = useState<PropertyList[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!user) { setLists([]); return; }
    setLoading(true);
    const { data } = await createClient()
      .from('property_lists')
      .select('*, property_list_items(count)')
      .order('created_at', { ascending: false });
    setLists(
      (data ?? []).map((l: Record<string, unknown>) => ({
        id: l.id,
        name: l.name,
        created_at: l.created_at,
        item_count: (l.property_list_items as { count: number }[])?.[0]?.count ?? 0,
      })) as PropertyList[]
    );
    setLoading(false);
  }, [user]);

  useEffect(() => { refresh(); }, [refresh]);

  async function createList(name: string) {
    if (!user) return null;
    const { data, error } = await createClient()
      .from('property_lists')
      .insert({ user_id: user.id, name })
      .select()
      .single();
    if (!error) await refresh();
    return error ? null : (data as PropertyList);
  }

  async function deleteList(id: string) {
    await createClient().from('property_lists').delete().eq('id', id);
    await refresh();
  }

  async function addToList(listId: string, county: string, parcelId: string) {
    const { error } = await createClient()
      .from('property_list_items')
      .upsert({ list_id: listId, county, parcel_id: parcelId });
    await refresh();
    return !error;
  }

  async function removeFromList(itemId: string) {
    await createClient().from('property_list_items').delete().eq('id', itemId);
    await refresh();
  }

  async function getListItems(listId: string): Promise<PropertyListItem[]> {
    const { data } = await createClient()
      .from('property_list_items')
      .select(`
        id, list_id, county, parcel_id, added_at,
        properties!inner(address, city, owner_name, assessed_value),
        scores(score, rank, scoring_mode)
      `)
      .eq('list_id', listId)
      .eq('scores.scoring_mode', 'broad')
      .order('added_at', { ascending: false });

    return (data ?? []).map((row: Record<string, unknown>) => {
      const prop = (row.properties as Record<string, unknown>) ?? {};
      const scoreRow = Array.isArray(row.scores) ? (row.scores[0] as Record<string, unknown>) : {};
      return {
        id: row.id as string,
        list_id: row.list_id as string,
        county: row.county as string,
        parcel_id: row.parcel_id as string,
        added_at: row.added_at as string,
        address: prop.address as string | null,
        city: prop.city as string | null,
        owner_name: prop.owner_name as string | null,
        assessed_value: prop.assessed_value as number | null,
        score: scoreRow?.score as number | undefined,
        rank: scoreRow?.rank as string | undefined,
      };
    });
  }

  async function isInAnyList(county: string, parcelId: string): Promise<string[]> {
    if (!user) return [];
    const { data } = await createClient()
      .from('property_list_items')
      .select('list_id')
      .eq('county', county)
      .eq('parcel_id', parcelId);
    return (data ?? []).map((r: { list_id: string }) => r.list_id);
  }

  async function exportList(listId: string, listName: string) {
    const items = await getListItems(listId);
    downloadCsv(
      `${listName.replace(/\s+/g, '_')}.csv`,
      items as unknown as Record<string, unknown>[],
      ['county', 'parcel_id', 'address', 'city', 'owner_name', 'assessed_value', 'score', 'rank', 'added_at']
    );
  }

  return { lists, loading, createList, deleteList, addToList, removeFromList, getListItems, isInAnyList, exportList, refresh };
}
