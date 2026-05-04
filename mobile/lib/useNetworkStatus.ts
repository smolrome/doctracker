import { useEffect, useState } from 'react';
import NetInfo, { NetInfoState } from '@react-native-community/netinfo';

type NetworkStatus = {
  isOnline: boolean;
  isOffline: boolean;
  /** True on first render before NetInfo has fired its first event */
  isUnknown: boolean;
};

/**
 * Lightweight hook that tracks real-time network connectivity.
 * isOnline is true only when both isConnected AND isInternetReachable are true.
 */
export function useNetworkStatus(): NetworkStatus {
  const [state, setState] = useState<NetInfoState | null>(null);

  useEffect(() => {
    // Fetch current state immediately
    NetInfo.fetch().then(setState);
    // Subscribe to future changes
    const unsubscribe = NetInfo.addEventListener(setState);
    return unsubscribe;
  }, []);

  if (state === null) {
    return { isOnline: true, isOffline: false, isUnknown: true };
  }

  const isOnline =
    state.isConnected === true && state.isInternetReachable !== false;

  return { isOnline, isOffline: !isOnline, isUnknown: false };
}
