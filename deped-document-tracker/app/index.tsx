import { useMemo, useState } from 'react';
import { Redirect } from 'expo-router';
import { useAuthStore } from '../lib/store';
import SplashScreen from './splash';

export default function Index() {
  const { isAuthenticated, isLoading } = useAuthStore();
  const [showSplash, setShowSplash] = useState(true);

  // Resolves when Zustand finishes its auth check.
  // useMemo ensures we create this Promise only once — not on every render.
  const initPromise = useMemo(
    () => new Promise<void>((resolve) => {
      // If already done by the time we mount, resolve immediately
      if (!isLoading) { resolve(); return; }

      // Otherwise poll until isLoading clears
      const interval = setInterval(() => {
        if (!useAuthStore.getState().isLoading) {
          clearInterval(interval);
          resolve();
        }
      }, 50);
    }),
    [] // created once on mount
  );

  if (showSplash) {
    return (
      <SplashScreen
        onFinish={() => setShowSplash(false)}
        initPromise={initPromise}
      />
    );
  }

  if (isAuthenticated) {
    return <Redirect href="/(app)/dashboard" />;
  }

  return <Redirect href="/(auth)/login" />;
}