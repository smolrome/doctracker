import AsyncStorage from '@react-native-async-storage/async-storage';
import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister';

/**
 * Persists the entire React Query cache to AsyncStorage so all fetched
 * data (documents, offices, dropdown options, staff lists, etc.) survives
 * app restarts and is available offline.
 */
export const queryPersister = createAsyncStoragePersister({
  storage: AsyncStorage,
  key: 'doctracker-rq-cache',
  // Throttle writes so we don't hammer AsyncStorage on every query update
  throttleTime: 1000,
});

/** How long persisted cache is considered valid (24 hours). */
export const PERSIST_MAX_AGE = 1000 * 60 * 60 * 24;
