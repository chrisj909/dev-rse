'use client';
import { useState, useEffect, useCallback } from 'react';
import { createClient } from '@/lib/supabase';
import { useAuth } from '@/contexts/AuthContext';
import { downloadCsv } from '@/lib/exportCsv';
import { SIGNAL_FILTERS } from '@/lib/signalFilters';

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
  state?: string | null;
  owner_name?: string | null;
  mailing_address?: string | null;
  assessed_value?: number | null;
  score?: number;
  rank?: string;
  signals?: string[];
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

  async function addManyToList(listId: string, items: { county: string; parcel_id: string }[]) {
    if (!items.length) return true;
    const { error } = await createClient()
      .from('property_list_items')
      .upsert(items.map(i => ({ list_id: listId, county: i.county, parcel_id: i.parcel_id })));
    await refresh();
    return !error;
  }

  async function removeFromList(itemId: string) {
    await createClient().from('property_list_items').delete().eq('id', itemId);
    await refresh();
  }

  async function getListItems(listId: string): Promise<PropertyListItem[]> {
    // Step 1: fetch list items (no FK to properties, so no PostgREST join available)
    const { data: items } = await createClient()
      .from('property_list_items')
      .select('id, list_id, county, parcel_id, added_at')
      .eq('list_id', listId)
      .order('added_at', { ascending: false });

    if (!items || items.length === 0) return [];

    // Step 2: fetch property details grouped by county
    const byCounty: Record<string, string[]> = {};
    for (const item of items as Record<string, unknown>[]) {
      const c = item.county as string;
      (byCounty[c] ??= []).push(item.parcel_id as string);
    }

    const propRows: Record<string, unknown>[] = [];
    await Promise.all(
      Object.entries(byCounty).map(async ([county, parcelIds]) => {
        const { data } = await createClient()
          .from('properties')
          .select('id, county, parcel_id, address, city, state, owner_name, mailing_address, assessed_value')
          .eq('county', county)
          .in('parcel_id', parcelIds);
        propRows.push(...((data ?? []) as Record<string, unknown>[]));
      })
    );

    const propMap: Record<string, Record<string, unknown>> = {};
    const propertyIds: string[] = [];
    for (const prop of propRows) {
      propMap[`${prop.county}:${prop.parcel_id}`] = prop;
      propertyIds.push(prop.id as string);
    }

    // Step 3: fetch broad scores for those property UUIDs
    const scoreMap: Record<string, { score: number; rank: string }> = {};
    const signalMap: Record<string, string[]> = {};
    if (propertyIds.length > 0) {
      const { data: scores } = await createClient()
        .from('scores')
        .select('property_id, score, rank')
        .in('property_id', propertyIds)
        .eq('scoring_mode', 'broad');
      for (const s of (scores ?? []) as Record<string, unknown>[]) {
        scoreMap[s.property_id as string] = { score: s.score as number, rank: s.rank as string };
      }

      const signalColumns = ['property_id', ...SIGNAL_FILTERS.map(signal => signal.value)].join(', ');
      const { data: signalRows } = await createClient()
        .from('signals')
        .select(signalColumns)
        .in('property_id', propertyIds);
      for (const signalRow of (signalRows ?? []) as unknown as Record<string, unknown>[]) {
        signalMap[signalRow.property_id as string] = SIGNAL_FILTERS
          .filter(signal => Boolean(signalRow[signal.value]))
          .map(signal => signal.value);
      }
    }

    return (items as Record<string, unknown>[]).map(item => {
      const key = `${item.county}:${item.parcel_id}`;
      const prop = propMap[key] ?? {};
      const scoreRow = prop.id ? scoreMap[prop.id as string] : undefined;
      return {
        id: item.id as string,
        list_id: item.list_id as string,
        county: item.county as string,
        parcel_id: item.parcel_id as string,
        added_at: item.added_at as string,
        address: (prop.address as string | null) ?? null,
        city: (prop.city as string | null) ?? null,
        state: (prop.state as string | null) ?? null,
        owner_name: (prop.owner_name as string | null) ?? null,
        mailing_address: (prop.mailing_address as string | null) ?? null,
        assessed_value: (prop.assessed_value as number | null) ?? null,
        score: scoreRow?.score,
        rank: scoreRow?.rank,
        signals: prop.id ? (signalMap[prop.id as string] ?? []) : [],
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
      items.map(item => ({
        county: item.county,
        parcel_id: item.parcel_id,
        address: item.address,
        city: item.city,
        state: item.state,
        owner_name: item.owner_name,
        mailing_address: item.mailing_address,
        assessed_value: item.assessed_value,
        score: item.score,
        rank: item.rank,
        active_signals: (item.signals ?? []).join(' | '),
        added_at: item.added_at,
      })),
      ['county', 'parcel_id', 'address', 'city', 'state', 'owner_name', 'mailing_address', 'assessed_value', 'score', 'rank', 'active_signals', 'added_at']
    );
  }

  return { lists, loading, createList, deleteList, addToList, addManyToList, removeFromList, getListItems, isInAnyList, exportList, refresh };
}
