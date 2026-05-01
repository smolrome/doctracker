import { useEffect, useRef } from 'react';
import { AppState, AppStateStatus } from 'react-native';
import { Slot } from 'expo-router';
import { QueryClient } from '@tanstack/react-query';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import * as Notifications from 'expo-notifications';
import { useAuthStore } from '../lib/store';
import { registerForPushNotifications } from '../lib/notifications';
import { cache } from '../lib/cache';
import { queryPersister, PERSIST_MAX_AGE } from '../lib/queryPersister';
import { OfflineBanner } from '../components/ui/OfflineBanner';
import { offlineQueue } from '../lib/offlineQueue';
import { useNetwork } from '../hooks/useNetwork';
import { prefetchAllData } from '../lib/prefetch';
import api from '../lib/api';

// ── QueryClient configured for offline-first use ─────────────────────────────
// gcTime must be >= PERSIST_MAX_AGE so data isn't garbage-collected before
// it can be read back from AsyncStorage on the next app start.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Serve cached data instantly; revalidate in background when online
      staleTime: 1000 * 60 * 5,       // 5 min — data is "fresh" for 5 min
      gcTime:    PERSIST_MAX_AGE,      // 24 h — keep in memory until persisted
      retry: (failureCount, error: any) => {
        // Don't retry client errors (4xx) — only transient/network errors
        if (error?.response?.status >= 400 && error?.response?.status < 500) return false;
        return failureCount < 2;
      },
      // Run query function even when offline; React Query returns the
      // persisted cache value if the network call fails
      networkMode: 'offlineFirst',
    },
    mutations: {
      networkMode: 'offlineFirst',
    },
  },
});

// ── Inner component so hooks can read auth state ──────────────────────────────
function AppShell() {
  const loadFromStorage = useAuthStore((s) => s.loadFromStorage);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isLoading       = useAuthStore((s) => s.isLoading);
  const { isOnline }    = useNetwork();
  const notificationListener = useRef<Notifications.EventSubscription | null>(null);
  const responseListener     = useRef<Notifications.EventSubscription | null>(null);
  const syncingRef = useRef(false);
  const prefetchedRef = useRef(false);

  useEffect(() => { loadFromStorage(); }, []);

  // Clear query cache + local cache on logout
  useEffect(() => {
    if (!isAuthenticated && !isLoading) {
      queryClient.clear();
      cache.clearAll();
    }
  }, [isAuthenticated, isLoading]);

  // Push notifications
  useEffect(() => {
    if (!isAuthenticated) return;
    registerForPushNotifications();

    notificationListener.current =
      Notifications.addNotificationReceivedListener((n) => {
        console.log('Notification:', n);
      });
    responseListener.current =
      Notifications.addNotificationResponseReceivedListener((r) => {
        console.log('Tapped:', r);
      });

    return () => {
      notificationListener.current?.remove();
      responseListener.current?.remove();
    };
  }, [isAuthenticated]);

  // ── Offline queue sync ──────────────────────────────────────────────────────
  // When the device comes back online, replay any document submissions that
  // were queued while offline.
  useEffect(() => {
    if (!isOnline || !isAuthenticated || syncingRef.current) return;

    (async () => {
      const pending = await offlineQueue.getAll();
      if (pending.length === 0) return;

      syncingRef.current = true;
      console.log(`[OfflineSync] Processing ${pending.length} queued submission(s)…`);

      for (const item of pending) {
        try {
          await api.post('/client/submit', item.payload);
          await offlineQueue.remove(item.queueId);
          // Invalidate docs so My Docs refreshes with the newly submitted doc
          queryClient.invalidateQueries({ queryKey: ['client-docs'] });
          queryClient.invalidateQueries({ queryKey: ['client-docs-all'] });
          console.log(`[OfflineSync] Synced queued submission ${item.queueId}`);
        } catch (err) {
          await offlineQueue.incrementRetry(item.queueId);
          console.warn(`[OfflineSync] Failed to sync ${item.queueId}:`, err);
        }
      }
      syncingRef.current = false;
    })();
  }, [isOnline, isAuthenticated]);

  // ── Proactive data prefetch ─────────────────────────────────────────────────
  // When online + authenticated, prefetch all data into the cache so everything
  // is available offline — even screens the user hasn't visited yet.
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    if (!isOnline || !isAuthenticated || prefetchedRef.current) return;
    prefetchedRef.current = true;
    prefetchAllData(queryClient, user?.role);
  }, [isOnline, isAuthenticated]);

  // Re-prefetch when the app returns to the foreground with connectivity
  useEffect(() => {
    if (!isAuthenticated) return;

    const handleAppState = (state: AppStateStatus) => {
      if (state === 'active' && isOnline) {
        prefetchAllData(queryClient, user?.role);
      }
    };

    const sub = AppState.addEventListener('change', handleAppState);
    return () => sub.remove();
  }, [isAuthenticated, isOnline]);

  // Reset prefetch flag on logout so next login triggers a fresh prefetch
  useEffect(() => {
    if (!isAuthenticated && !isLoading) {
      prefetchedRef.current = false;
    }
  }, [isAuthenticated, isLoading]);

  return (
    <>
      <OfflineBanner />
      <Slot />
    </>
  );
}

// ── Root layout ───────────────────────────────────────────────────────────────
export default function RootLayout() {
  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister: queryPersister,
        maxAge: PERSIST_MAX_AGE,
        dehydrateOptions: {
          shouldDehydrateQuery: (query) => {
            // Only persist queries that completed successfully — never persist
            // pending/loading queries (they'd be retried on restore and fail
            // with "dehydrated as pending ended up rejecting" console errors)
            if (query.state.status !== 'success') return false;
            const key = query.queryKey[0] as string;
            // Exclude ephemeral / auth / one-shot queries that don't make
            // sense to cache across sessions
            const exclude = ['auth', 'login', 'refresh', 'qr'];
            return !exclude.includes(key);
          },
        },
      }}
    >
      <AppShell />
    </PersistQueryClientProvider>
  );
}