import { useEffect, useRef, useState } from 'react';
import { Alert, AppState, AppStateStatus, Linking, Platform } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import * as FileSystem from 'expo-file-system/legacy';
import * as IntentLauncher from 'expo-intent-launcher';
import { Slot } from 'expo-router';
import { QueryClient } from '@tanstack/react-query';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import Constants from 'expo-constants';
import { useAuthStore } from '../lib/store';
import { registerForPushNotifications } from '../lib/notifications';
import { cache } from '../lib/cache';
import { queryPersister, PERSIST_MAX_AGE } from '../lib/queryPersister';
import { OfflineBanner } from '../components/ui/OfflineBanner';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { offlineQueue } from '../lib/offlineQueue';
import { useNetwork } from '../hooks/useNetwork';
import { useAppVersion } from '../hooks/useAppVersion';
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
        const status = error?.response?.status;
        // 429 is handled by the axios interceptor with backoff — React Query
        // should not add its own retries on top, or it will re-queue a request
        // that is already being retried transparently.
        if (status === 429) return false;
        // Don't retry other client errors (4xx)
        if (status >= 400 && status < 500) return false;
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
  const notificationListener = useRef<{ remove: () => void } | null>(null);
  const responseListener     = useRef<{ remove: () => void } | null>(null);
  const syncingRef = useRef(false);
  // Track when the last prefetch ran so foreground re-prefetches are throttled.
  // Using a timestamp ref instead of a boolean flag allows re-prefetching after
  // a cooldown period rather than never again per session.
  const lastPrefetchAt = useRef<number>(0);
  const PREFETCH_COOLDOWN_MS = 1000 * 60 * 5; // 5 minutes between prefetches

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
    const isExpoGo = Constants.appOwnership === 'expo';
    if (isExpoGo) return;
    const Notifications = require('expo-notifications');
    registerForPushNotifications();

    notificationListener.current =
      Notifications.addNotificationReceivedListener((n: any) => {
        console.log('Notification:', n);
      });
    responseListener.current =
      Notifications.addNotificationResponseReceivedListener((r: any) => {
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
  // A 5-minute cooldown prevents hammering the API when the user backgrounds
  // and foregrounds the app rapidly (which was causing 429 rate-limit errors).
  const user = useAuthStore((s) => s.user);

  const runPrefetchIfDue = () => {
    const now = Date.now();
    if (now - lastPrefetchAt.current < PREFETCH_COOLDOWN_MS) return;
    lastPrefetchAt.current = now;
    prefetchAllData(queryClient, user?.role);
  };

  // Initial prefetch on login / first online moment
  useEffect(() => {
    if (!isOnline || !isAuthenticated) return;
    runPrefetchIfDue();
  }, [isOnline, isAuthenticated]);

  // Re-prefetch when the app returns to the foreground (throttled)
  useEffect(() => {
    if (!isAuthenticated) return;

    const handleAppState = (state: AppStateStatus) => {
      if (state === 'active' && isOnline) {
        runPrefetchIfDue();
      }
    };

    const sub = AppState.addEventListener('change', handleAppState);
    return () => sub.remove();
  }, [isAuthenticated, isOnline]);

  // Reset cooldown on logout so the next login triggers a fresh prefetch immediately
  useEffect(() => {
    if (!isAuthenticated && !isLoading) {
      lastPrefetchAt.current = 0;
    }
  }, [isAuthenticated, isLoading]);

  // ── App version check ───────────────────────────────────────────────────────
  const { mustUpdate, needsUpdate, downloadUrl, releaseNotes, latestVersion, checked } =
    useAppVersion();

  // Soft-update dialog: user can dismiss once per session
  const [softDismissed, setSoftDismissed] = useState(false);

  const showMustUpdate = checked && mustUpdate;
  const showSoftUpdate = checked && needsUpdate && !softDismissed;

  const openDownload = async () => {
    const url = downloadUrl || 'https://doctracker.depedleytepersonnelunit.com/download';

    if (Platform.OS !== 'android') {
      try {
        const supported = await Linking.canOpenURL(url);
        if (supported) {
          await Linking.openURL(url);
        } else {
          Alert.alert('Error', 'Cannot open download page. Please visit:\n' + url);
        }
      } catch {
        Alert.alert('Error', 'Could not open download page. Please try again.');
      }
      return;
    }

    try {
      Alert.alert('Downloading Update', 'Downloading APK, please wait…');
      const dest = FileSystem.documentDirectory + 'doctracker-update.apk';
      const { uri } = await FileSystem.downloadAsync(url, dest);
      await IntentLauncher.startActivityAsync('android.intent.action.VIEW', {
        data: uri,
        flags: 1,
        type: 'application/vnd.android.package-archive',
      });
    } catch (e) {
      console.error('APK download/install error:', e);
      Alert.alert('Error', 'Could not download or open the update. Please try again.');
    }
  };

  const copyDownloadLink = async () => {
    const url = downloadUrl || 'https://doctracker.depedleytepersonnelunit.com/download';
    try {
      await Clipboard.setStringAsync(url);
      Alert.alert('Link Copied', 'Link copied! Paste it in your browser.');
    } catch {
      Alert.alert('Error', 'Could not copy link. Please write it down:\n' + url);
    }
  };

  return (
    <>
      <OfflineBanner />
      <Slot />

      {/* ── Force-update dialog (blocking — cannot be dismissed) ─────────── */}
      <ConfirmDialog
        visible={showMustUpdate}
        onClose={() => {}}           // intentionally no-op — user must update
        icon="🔄"
        accentColor="#0038A8"
        title="Update Required"
        message={`Your current version is no longer supported. Please update to version ${latestVersion} to continue.\n\n${releaseNotes ? releaseNotes + '\n\n' : ''}Tap "Download Update" to open the download page. Download and install the APK to update.`}
        buttons={[
          {
            label: 'Download Update',
            variant: 'default',
            onPress: openDownload,
          },
          {
            label: 'Copy Download Link',
            variant: 'ghost',
            onPress: copyDownloadLink,
          },
        ]}
      />

      {/* ── Soft-update dialog (dismissible) ────────────────────────────── */}
      <ConfirmDialog
        visible={!showMustUpdate && showSoftUpdate}
        onClose={() => setSoftDismissed(true)}
        icon="✨"
        accentColor="#0038A8"
        title="New Version Available"
        message={`Version ${latestVersion} is available.\n\n${releaseNotes ? releaseNotes + '\n\n' : ''}Tap "Update" to open the download page. Download and install the APK to update.`}
        buttons={[
          {
            label: 'Not Now',
            variant: 'ghost',
            onPress: () => setSoftDismissed(true),
          },
          {
            label: 'Update',
            variant: 'default',
            onPress: openDownload,
          },
        ]}
      />
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
            // Exclude ephemeral queries AND large datasets that are
            // persisted separately via the file-system cache
            const exclude = ['auth', 'login', 'refresh', 'qr', 'documents', 'client-docs', 'client-docs-all'];
            return !exclude.includes(key);
          },
        },
      }}
    >
      <AppShell />
    </PersistQueryClientProvider>
  );
}