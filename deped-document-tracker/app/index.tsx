import { useState } from 'react';
import { Redirect } from 'expo-router';
import { useAuthStore } from '../lib/store';
import SplashScreen from './splash';

export default function Index() {
  const { isAuthenticated, isLoading } = useAuthStore();
  const [showSplash, setShowSplash] = useState(true);

  if (showSplash || isLoading) {
    return <SplashScreen onFinish={() => setShowSplash(false)} />;
  }

  if (isAuthenticated) {
    return <Redirect href="/(app)/dashboard" />;
  }

  return <Redirect href="/(auth)/login" />;
}