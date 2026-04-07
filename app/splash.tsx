import { useEffect, useRef } from 'react';
import {
  View,
  Text,
  Image,
  Animated,
  StatusBar,
} from 'react-native';

interface SplashScreenProps {
  onFinish: () => void;
}

export default function SplashScreen({ onFinish }: SplashScreenProps) {
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const scaleAnim = useRef(new Animated.Value(0.7)).current;
  const slideAnim = useRef(new Animated.Value(30)).current;
  const exitAnim = useRef(new Animated.Value(1)).current;

  const circle1X = useRef(new Animated.Value(0)).current;
  const circle1Y = useRef(new Animated.Value(0)).current;
  const circle2X = useRef(new Animated.Value(0)).current;
  const circle2Y = useRef(new Animated.Value(0)).current;
  const circle3X = useRef(new Animated.Value(0)).current;
  const circle3Y = useRef(new Animated.Value(0)).current;

  const drift = (anim: Animated.Value, range: number, duration: number) =>
    Animated.loop(
      Animated.sequence([
        Animated.timing(anim, { toValue: range, duration, useNativeDriver: true }),
        Animated.timing(anim, { toValue: -range, duration, useNativeDriver: true }),
        Animated.timing(anim, { toValue: 0, duration: duration * 0.6, useNativeDriver: true }),
      ])
    );

  useEffect(() => {
    drift(circle1X, 18, 6000).start();
    drift(circle1Y, 14, 7500).start();
    drift(circle2X, 12, 8000).start();
    drift(circle2Y, 20, 6500).start();
    drift(circle3X, 20, 7000).start();
    drift(circle3Y, 16, 9000).start();

    Animated.parallel([
      Animated.timing(fadeAnim, { toValue: 1, duration: 800, useNativeDriver: true }),
      Animated.spring(scaleAnim, { toValue: 1, tension: 50, friction: 8, useNativeDriver: true }),
      Animated.spring(slideAnim, { toValue: 0, tension: 60, friction: 10, useNativeDriver: true }),
    ]).start();

    const timer = setTimeout(() => {
      Animated.timing(exitAnim, {
        toValue: 0,
        duration: 500,
        useNativeDriver: true,
      }).start(() => onFinish());
    }, 2500);

    return () => clearTimeout(timer);
  }, []);

  return (
    <Animated.View style={{
      flex: 1,
      backgroundColor: '#F0F4FF',
      alignItems: 'center',
      justifyContent: 'center',
      opacity: exitAnim,
    }}>
      <StatusBar barStyle="dark-content" backgroundColor="#F0F4FF" />

      <Animated.View style={{
        position: 'absolute', top: -60, right: -60,
        width: 220, height: 220, borderRadius: 110,
        backgroundColor: '#0038A8', opacity: 0.06,
        transform: [{ translateX: circle1X }, { translateY: circle1Y }],
      }} />
      <Animated.View style={{
        position: 'absolute', top: 80, right: -30,
        width: 120, height: 120, borderRadius: 60,
        backgroundColor: '#FCD116', opacity: 0.12,
        transform: [{ translateX: circle2X }, { translateY: circle2Y }],
      }} />
      <Animated.View style={{
        position: 'absolute', bottom: -80, left: -50,
        width: 260, height: 260, borderRadius: 130,
        backgroundColor: '#0038A8', opacity: 0.05,
        transform: [{ translateX: circle3X }, { translateY: circle3Y }],
      }} />

      <Animated.View style={{
        alignItems: 'center',
        opacity: fadeAnim,
        transform: [
          { scale: scaleAnim },
          { translateY: slideAnim },
        ],
      }}>
        <View style={{
          width: 120, height: 120, borderRadius: 60,
          backgroundColor: '#fff',
          alignItems: 'center', justifyContent: 'center',
          marginBottom: 8,
          shadowColor: '#0038A8',
          shadowOffset: { width: 0, height: 8 },
          shadowOpacity: 0.25,
          shadowRadius: 16,
          elevation: 12,
          overflow: 'hidden',
        }}>
          <Image
            source={require('../assets/icon.png')}
            style={{ width: 120, height: 120, resizeMode: 'cover' }}
          />
        </View>

        <View style={{
          flexDirection: 'row',
          marginBottom: 20,
          borderRadius: 2,
          overflow: 'hidden',
        }}>
          <View style={{ width: 32, height: 4, backgroundColor: '#0038A8' }} />
          <View style={{ width: 32, height: 4, backgroundColor: '#CE1126' }} />
          <View style={{ width: 32, height: 4, backgroundColor: '#FCD116' }} />
        </View>

        <Text style={{
          fontSize: 28,
          fontWeight: '900',
          color: '#0038A8',
          letterSpacing: -0.5,
          textAlign: 'center',
        }}>
          DepEd Leyte
        </Text>
        <Text style={{
          fontSize: 14,
          color: '#64748B',
          marginTop: 6,
          textAlign: 'center',
          letterSpacing: 0.3,
        }}>
          Document Tracker
        </Text>
        <Text style={{
          fontSize: 12,
          color: '#94A3B8',
          marginTop: 2,
          textAlign: 'center',
          letterSpacing: 0.5,
        }}>
          Personnel Unit
        </Text>

        <View style={{
          flexDirection: 'row',
          gap: 6,
          marginTop: 40,
        }}>
          {[0, 1, 2].map((i) => (
            <LoadingDot key={i} delay={i * 200} />
          ))}
        </View>
      </Animated.View>

      <Text style={{
        position: 'absolute',
        bottom: 40,
        color: '#94A3B8',
        fontSize: 11,
        letterSpacing: 0.3,
      }}>
        DepEd Division of Leyte
      </Text>
    </Animated.View>
  );
}

function LoadingDot({ delay }: { delay: number }) {
  const anim = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    setTimeout(() => {
      Animated.loop(
        Animated.sequence([
          Animated.timing(anim, { toValue: 1, duration: 400, useNativeDriver: true }),
          Animated.timing(anim, { toValue: 0.3, duration: 400, useNativeDriver: true }),
        ])
      ).start();
    }, delay);
  }, []);

  return (
    <Animated.View style={{
      width: 8, height: 8, borderRadius: 4,
      backgroundColor: '#0038A8',
      opacity: anim,
    }} />
  );
}
