import { useEffect, useRef, useState } from 'react';
import { Animated, Text, View } from 'react-native';
import { WifiOff, Wifi } from 'lucide-react-native';
import { useNetwork } from '../../hooks/useNetwork';

/**
 * Slides in from the top when the device goes offline.
 * Briefly shows "Back online" when connectivity is restored, then slides out.
 */
export function OfflineBanner() {
  const { isOnline, isChecking } = useNetwork();
  const translateY = useRef(new Animated.Value(-60)).current;
  const [visible, setVisible] = useState(false);
  const [showingOnline, setShowingOnline] = useState(false);
  const wasOfflineRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (isChecking) return;

    if (!isOnline) {
      // Going offline — slide banner in
      if (timerRef.current) clearTimeout(timerRef.current);
      wasOfflineRef.current = true;
      setShowingOnline(false);
      setVisible(true);
      Animated.spring(translateY, {
        toValue: 0, useNativeDriver: true, tension: 80, friction: 10,
      }).start();
    } else if (wasOfflineRef.current) {
      // Back online — swap text, then slide out after 2.5 s
      setShowingOnline(true);
      timerRef.current = setTimeout(() => {
        Animated.timing(translateY, {
          toValue: -60, duration: 280, useNativeDriver: true,
        }).start(() => {
          setVisible(false);
          setShowingOnline(false);
          wasOfflineRef.current = false;
        });
      }, 2500);
    }

    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [isOnline, isChecking]);

  if (!visible) return null;

  return (
    <Animated.View style={{
      position: 'absolute', top: 0, left: 0, right: 0,
      zIndex: 9999, transform: [{ translateY }],
    }}>
      <View style={{
        backgroundColor: showingOnline ? '#16A34A' : '#1E293B',
        paddingTop: 50, paddingBottom: 10, paddingHorizontal: 16,
        flexDirection: 'row', alignItems: 'center', gap: 8,
      }}>
        {showingOnline
          ? <Wifi size={15} color="#fff" />
          : <WifiOff size={15} color="#fff" />}
        <Text style={{ color: '#fff', fontWeight: '700', fontSize: 13 }}>
          {showingOnline
            ? '✅ Back online — syncing & caching data…'
            : '📵 You\'re offline — showing cached data'}
        </Text>
      </View>
    </Animated.View>
  );
}