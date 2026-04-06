import { useState, useEffect } from 'react';
import NetInfo from '@react-native-community/netinfo';

export function useNetwork() {
  const [isOnline, setIsOnline] = useState(true);
  const [isChecking, setIsChecking] = useState(true);

  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener((state) => {
      setIsOnline(!!state.isConnected && !!state.isInternetReachable);
      setIsChecking(false);
    });

    return unsubscribe;
  }, []);

  return { isOnline, isChecking };
}