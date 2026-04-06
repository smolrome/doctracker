import { View, Text, Animated } from 'react-native';
import { useNetwork } from '../../hooks/useNetwork';
import { useEffect, useRef } from 'react';

export function OfflineBanner() {
  const { isOnline, isChecking } = useNetwork();
  const translateY = useRef(new Animated.Value(-50)).current;

  useEffect(() => {
    if (!isChecking) {
      Animated.timing(translateY, {
        toValue: isOnline ? -50 : 0,
        duration: 300,
        useNativeDriver: true,
      }).start();
    }
  }, [isOnline, isChecking]);

  return (
    <Animated.View
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 999,
        transform: [{ translateY }],
        backgroundColor: '#EF4444',
        paddingVertical: 8,
        paddingHorizontal: 16,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
      }}
    >
      <Text style={{ fontSize: 16 }}>📵</Text>
      <Text style={{ color: '#fff', fontWeight: '600', fontSize: 13 }}>
        You're offline — showing cached data
      </Text>
    </Animated.View>
  );
}