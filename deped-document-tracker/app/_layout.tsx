import { useEffect, useRef } from 'react';
import { Slot } from 'expo-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as Notifications from 'expo-notifications';
import { useAuthStore } from '../lib/store';
import { registerForPushNotifications } from '../lib/notifications';
import '../global.css';

const queryClient = new QueryClient();

export default function RootLayout() {
  const loadFromStorage = useAuthStore((s) => s.loadFromStorage);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const notificationListener = useRef<any>();
  const responseListener = useRef<any>();

  useEffect(() => {
    loadFromStorage();
  }, []);

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