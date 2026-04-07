import { useEffect, useRef, useState } from 'react';
import { Slot } from 'expo-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as Notifications from 'expo-notifications';
import { useAuthStore } from '../lib/store';
import { registerForPushNotifications } from '../lib/notifications';
import { cache } from '../lib/cache';

export default function RootLayout() {
  const loadFromStorage = useAuthStore((s) => s.loadFromStorage);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isLoading = useAuthStore((s) => s.isLoading);
  const [queryClient] = useState(() => new QueryClient());
  const notificationListener = useRef<Notifications.EventSubscription | null>(null);
  const responseListener = useRef<Notifications.EventSubscription | null>(null);

  useEffect(() => {
    loadFromStorage();
  }, []);

  useEffect(() => {
    if (!isAuthenticated && !isLoading) {
      queryClient.clear();
      cache.clearAll();
    }
  }, [isAuthenticated, isLoading]);

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

  return (
    <QueryClientProvider client={queryClient}>
      <Slot />
    </QueryClientProvider>
  );
}