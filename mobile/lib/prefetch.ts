import { QueryClient } from '@tanstack/react-query';
import api from './api';
import { cache } from './cache';
import { DocumentsResponse } from './types';

/**
 * Prefetch all key data into React Query cache + manual cache so everything
 * is available offline even if the user hasn't visited every screen yet.
 */
export async function prefetchAllData(
  queryClient: QueryClient,
  role?: string
) {
  console.log('[Prefetch] Starting background data prefetch…');
  const results = { succeeded: 0, failed: 0 };

  const prefetchQuery = async (
    key: string[],
    fn: () => Promise<any>,
    cacheKey?: string
  ) => {
    try {
      const data = await fn();
      queryClient.setQueryData(key, data);
      if (cacheKey) await cache.set(cacheKey, data);
      results.succeeded++;
    } catch (err) {
      results.failed++;
      console.warn(`[Prefetch] Failed to prefetch ${key[0]}:`, err);
    }
  };

  const isStaff = role !== 'client';

  const tasks: Promise<void>[] = [];

  // ── Data used by both staff and clients ─────────────────────────────────

  tasks.push(
    prefetchQuery(
      ['offices'],
      async () => {
        const res = await api.get('/offices');
        return (res.data ?? []) as Array<{ office_name: string; office_slug: string }>;
      },
      cache.KEYS.OFFICES
    )
  );

  tasks.push(
    prefetchQuery(
      ['dropdown-options'],
      async () => {
        const res = await api.get('/dropdown-options');
        const raw: Record<string, unknown> = res.data ?? {};
        const normalized: Record<string, string[]> = {};
        for (const [key, val] of Object.entries(raw)) {
          if (Array.isArray(val)) {
            normalized[key] = val as string[];
          } else if (val && typeof val === 'object' && Array.isArray((val as any).options)) {
            normalized[key] = (val as any).options as string[];
          }
        }
        return normalized;
      }
    )
  );

  // ── Staff-only data ─────────────────────────────────────────────────────

  if (isStaff) {
    // First page of documents — enough for instant render; the list screen handles full pagination
    tasks.push(
      prefetchQuery(
        ['documents', '', '', 'All', true],
        async () => {
          const res = await api.get('/documents', { params: { page: 1, limit: 200 } });
          return res.data as DocumentsResponse;
        },
        cache.KEYS.DOCUMENTS
      )
    );

    tasks.push(
      prefetchQuery(
        ['stats', '', true],
        async () => {
          const res = await api.get('/stats');
          return res.data;
        },
        cache.KEYS.STATS
      )
    );

    tasks.push(
      prefetchQuery(
        ['staff'],
        async () => {
          const res = await api.get('/staff');
          return (res.data ?? []) as Array<{
            username: string;
            full_name: string;
            office: string;
            role: string;
          }>;
        }
      )
    );

    tasks.push(
      prefetchQuery(
        ['pending-count'],
        async () => {
          const res = await api.get('/pending-count');
          return (res.data?.count ?? 0) as number;
        }
      )
    );
  }

  // ── Client-only data ────────────────────────────────────────────────────

  if (!isStaff) {
    tasks.push(
      prefetchQuery(
        ['client-docs-all'],
        async () => {
          const res = await api.get('/client/documents');
          return (res.data?.documents ?? []) as any[];
        }
      )
    );

    tasks.push(
      prefetchQuery(
        ['client-docs', '', 'All'],
        async () => {
          const res = await api.get('/client/documents');
          return (res.data?.documents ?? []) as any[];
        }
      )
    );
  }

  // ── Prefetch office staff for each office (for submit form) ─────────────
  if (!isStaff) {
    try {
      const officesRes = await api.get('/offices');
      const offices = (officesRes.data ?? []) as Array<{
        office_name: string;
        office_slug: string;
      }>;
      for (const office of offices) {
        tasks.push(
          prefetchQuery(
            ['office-staff', office.office_slug],
            async () => {
              const res = await api.get(`/offices/${office.office_slug}/staff`);
              return res.data;
            }
          )
        );
      }
    } catch {
      // offices list failed — staff prefetch skipped
    }
  }

  // Run tasks in small batches (3 at a time) with a short pause between each
  // batch to avoid firing all requests simultaneously and hitting the API rate
  // limit (60 req / 60 s). Sequential batching keeps the total request burst
  // well within safe bounds.
  const BATCH_SIZE = 3;
  const BATCH_DELAY_MS = 400;

  for (let i = 0; i < tasks.length; i += BATCH_SIZE) {
    await Promise.allSettled(tasks.slice(i, i + BATCH_SIZE));
    if (i + BATCH_SIZE < tasks.length) {
      await new Promise((r) => setTimeout(r, BATCH_DELAY_MS));
    }
  }

  await cache.updateLastSync();

  console.log(
    `[Prefetch] Done — ${results.succeeded} succeeded, ${results.failed} failed`
  );
}
