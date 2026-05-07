import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '../lib/api';
import { cache } from '../lib/cache';
import { useNetwork } from './useNetwork';
import { useAuthStore } from '../lib/store';

export interface DocumentFilters {
  office?: string;
  cat?: string;
  staff?: string;
  source?: string;    // 'Staff' | 'Client'
  date_from?: string; // YYYY-MM-DD
  date_to?: string;   // YYYY-MM-DD
}

export function useDocuments(search = '', status = 'All', filters?: DocumentFilters) {
  const { isOnline } = useNetwork();
  const [isFromCache, setIsFromCache] = useState(false);
  const user = useAuthStore((s) => s.user);
  const userId = user?.id || user?.username || '';

  const fetchDocuments = async () => {
    if (!isOnline) {
      const cached = await cache.getStale(cache.KEYS.DOCUMENTS);
      if (cached) {
        setIsFromCache(true);
        return cached;
      }
      throw new Error('No internet connection and no cached data available.');
    }

    try {
      const PAGE_SIZE = 200;
      const params: any = { limit: PAGE_SIZE, page: 1 };
      if (search) params.search = search;
      if (status !== 'All') params.status = status;
      if (filters?.office) params.office = filters.office;
      if (filters?.cat) params.cat = filters.cat;
      if (filters?.staff) params.staff = filters.staff;
      if (filters?.source) params.source = filters.source;
      if (filters?.date_from) params.date_from = filters.date_from;
      if (filters?.date_to) params.date_to = filters.date_to;

      const firstRes = await api.get('/documents', { params });
      const firstData = firstRes.data;
      const total = firstData.total ?? 0;
      const allDocs = [...(firstData.documents ?? [])];

      // Fetch remaining pages in parallel
      if (allDocs.length < total) {
        const totalPages = Math.ceil(total / PAGE_SIZE);
        const pagePromises = [];
        for (let p = 2; p <= totalPages; p++) {
          pagePromises.push(
            api.get('/documents', { params: { ...params, page: p } })
          );
        }
        const results = await Promise.all(pagePromises);
        for (const r of results) {
          allDocs.push(...(r.data.documents ?? []));
        }
      }

      const data = { documents: allDocs, total, page: 1, limit: total };

      // Only cache the base (unfiltered) fetch to preserve offline integrity
      const isBaseFetch =
        !search && status === 'All' &&
        !filters?.office && !filters?.cat &&
        !filters?.staff && !filters?.source &&
        !filters?.date_from && !filters?.date_to;
      if (isBaseFetch) {
        await cache.set(cache.KEYS.DOCUMENTS, data);
        await cache.updateLastSync();
      }
      setIsFromCache(false);

      return data;
    } catch (err) {
      const cached = await cache.getStale(cache.KEYS.DOCUMENTS);
      if (cached) {
        setIsFromCache(true);
        return cached;
      }
      throw err;
    }
  };

  const query = useQuery({
    queryKey: [
      'documents', userId, search, status,
      filters?.office, filters?.cat, filters?.staff, filters?.source,
      filters?.date_from, filters?.date_to,
      isOnline,
    ],
    queryFn: fetchDocuments,
    staleTime: 1000 * 60 * 5,
    retry: isOnline ? 2 : 0,
  });

  return { ...query, isFromCache };
}

export function useStats() {
  const { isOnline } = useNetwork();
  const [isFromCache, setIsFromCache] = useState(false);
  const user = useAuthStore((s) => s.user);
  const userId = user?.id || user?.username || '';

  const fetchStats = async () => {
    if (!isOnline) {
      const cached = await cache.getStale(cache.KEYS.STATS);
      if (cached) {
        setIsFromCache(true);
        return cached;
      }
      throw new Error('Offline');
    }

    try {
      const res = await api.get('/stats');
      await cache.set(cache.KEYS.STATS, res.data);
      setIsFromCache(false);
      return res.data;
    } catch (err) {
      const cached = await cache.getStale(cache.KEYS.STATS);
      if (cached) {
        setIsFromCache(true);
        return cached;
      }
      throw err;
    }
  };

  const query = useQuery({
    queryKey: ['stats', userId, isOnline],
    queryFn: fetchStats,
    staleTime: 1000 * 60 * 5,
    retry: isOnline ? 2 : 0,
  });

  return { ...query, isFromCache };
}