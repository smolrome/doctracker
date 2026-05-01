import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '../lib/api';
import { cache } from '../lib/cache';
import { useNetwork } from './useNetwork';
import { useAuthStore } from '../lib/store';

export function useDocuments(search = '', status = 'All') {
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

      await cache.set(cache.KEYS.DOCUMENTS, data);
      await cache.updateLastSync();
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
    queryKey: ['documents', userId, search, status, isOnline],
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