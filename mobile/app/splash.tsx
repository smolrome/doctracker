import { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  Image,
  Animated,
  StatusBar,
  TouchableOpacity,
} from 'react-native';
// FIX 1: Removed unused `Dimensions` import

interface SplashScreenProps {
  onFinish: () => void;
  initPromise?: Promise<void>;
}

const STATUS_STEPS = [
  'Checking connection…',
  'Loading resources…',
  'Almost ready…',
];

type ScreenState = 'loading' | 'error';

export default function SplashScreen({ onFinish, initPromise }: SplashScreenProps) {
  const fadeAnim   = useRef(new Animated.Value(0)).current;
  const scaleAnim  = useRef(new Animated.Value(0.82)).current;
  const slideAnim  = useRef(new Animated.Value(24)).current;
  const exitAnim   = useRef(new Animated.Value(1)).current;
  const accentScale1 = useRef(new Animated.Value(1)).current;
  const accentScale2 = useRef(new Animated.Value(1)).current;

  const [statusMessage, setStatusMessage] = useState(STATUS_STEPS[0]);
  // FIX 2: Track error state so we can show a retry UI on rejected initPromise
  const [screenState, setScreenState] = useState<ScreenState>('loading');
  // FIX 4: Track logo load failure to render an initials fallback
  const [logoError, setLogoError] = useState(false);

  const startInit = () => {
    setScreenState('loading');
    setStatusMessage(STATUS_STEPS[0]);

    const doExit = () => {
      Animated.timing(exitAnim, { toValue: 0, duration: 500, useNativeDriver: true })
        .start(() => onFinish());
    };

    // FIX 3: Status messages only cycle when no initPromise is provided (fixed timer).
    // When initPromise IS provided, the messages are generic and don't pretend to map
    // to real steps — a real implementation should resolve progress via callbacks/events.
    let msgTimers: ReturnType<typeof setTimeout>[] = [];

    if (initPromise) {
      // Single neutral message so we don't lie about progress
      setStatusMessage('Starting up…');
      const minDelay = new Promise<void>(res => setTimeout(res, 1500));
      Promise.all([initPromise, minDelay])
        .then(doExit)
        .catch(() => {
          // FIX 2: On rejection, show error state instead of silently exiting
          setScreenState('error');
          setStatusMessage('Something went wrong.');
        });
    } else {
      // Fallback fixed-timer path — cycling messages are fine here
      msgTimers = [
        setTimeout(() => setStatusMessage(STATUS_STEPS[1]), 900),
        setTimeout(() => setStatusMessage(STATUS_STEPS[2]), 1800),
      ];
      setTimeout(doExit, 2500);
    }

    return () => msgTimers.forEach(clearTimeout);
  };

  useEffect(() => {
    // Breathing pulses
    Animated.loop(
      Animated.sequence([
        Animated.timing(accentScale1, { toValue: 1.15, duration: 4000, useNativeDriver: true }),
        Animated.timing(accentScale1, { toValue: 1,    duration: 4000, useNativeDriver: true }),
      ])
    ).start();
    Animated.loop(
      Animated.sequence([
        Animated.timing(accentScale2, { toValue: 1.10, duration: 5200, useNativeDriver: true }),
        Animated.timing(accentScale2, { toValue: 1,    duration: 5200, useNativeDriver: true }),
      ])
    ).start();

    // Entry animation
    Animated.parallel([
      Animated.timing(fadeAnim,  { toValue: 1, duration: 700, useNativeDriver: true }),
      Animated.spring(scaleAnim, { toValue: 1, tension: 50, friction: 8,  useNativeDriver: true }),
      Animated.spring(slideAnim, { toValue: 0, tension: 60, friction: 10, useNativeDriver: true }),
    ]).start();

    const cleanup = startInit();
    return cleanup;
  }, []);

  return (
    <Animated.View style={{
      flex: 1,
      backgroundColor: '#0038A8',
      alignItems: 'center',
      justifyContent: 'center',
      opacity: exitAnim,
    }}>
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />

      {/* Accent circle — top right (yellow) */}
      <Animated.View style={{
        position: 'absolute', top: -56, right: -56,
        width: 220, height: 220, borderRadius: 110,
        backgroundColor: '#FCD116', opacity: 0.10,
        transform: [{ scale: accentScale1 }],
      }} />

      {/* Accent circle — bottom left (red) */}
      <Animated.View style={{
        position: 'absolute', bottom: -70, left: -50,
        width: 240, height: 240, borderRadius: 120,
        backgroundColor: '#CE1126', opacity: 0.10,
        transform: [{ scale: accentScale2 }],
      }} />

      {/* Logo + text block */}
      <Animated.View style={{
        alignItems: 'center',
        opacity: fadeAnim,
        transform: [{ scale: scaleAnim }, { translateY: slideAnim }],
      }}>

        <View style={{
          width: 108, height: 108, borderRadius: 54,
          backgroundColor: 'rgba(255,255,255,0.12)',
          alignItems: 'center', justifyContent: 'center',
          marginBottom: 20,
        }}>
          <View style={{
            width: 108, height: 108, borderRadius: 54,
            backgroundColor: '#fff',
            alignItems: 'center', justifyContent: 'center',
            overflow: 'hidden',
          }}>
            {logoError ? (
              <Text style={{ fontSize: 28, fontWeight: '700', color: '#0038A8' }}>DL</Text>
            ) : (
              <Image
                source={require('../assets/wow.png')}
                style={{ width: 108, height: 108, resizeMode: 'cover' }}
                onError={() => setLogoError(true)}
              />
            )}
          </View>
        </View>

        <Text style={{
          fontSize: 26,
          fontWeight: '900',
          color: '#fff',
          letterSpacing: -0.5,
          textAlign: 'center',
        }}>
          DepEd Leyte
        </Text>

        <Text style={{
          fontSize: 16,
          color: 'rgba(255,255,255,0.90)',
          marginTop: 6,
          textAlign: 'center',
          letterSpacing: 0.3,
        }}>
          Document Tracker
        </Text>

        <Text style={{
          fontSize: 13,
          color: 'rgba(255,255,255,0.55)',
          marginTop: 3,
          textAlign: 'center',
          letterSpacing: 0.5,
        }}>
          Personnel Unit
        </Text>

        {/* FIX 2: Show retry button on error, dots only while loading */}
        {screenState === 'loading' ? (
          <View style={{ flexDirection: 'row', gap: 6, marginTop: 28 }}>
            {[0, 1, 2].map((i) => (
              <LoadingDot key={i} delay={i * 200} />
            ))}
          </View>
        ) : (
          <TouchableOpacity
            onPress={startInit}
            style={{
              marginTop: 28,
              paddingHorizontal: 24,
              paddingVertical: 10,
              borderRadius: 20,
              borderWidth: 1,
              borderColor: 'rgba(255,255,255,0.5)',
            }}
          >
            <Text style={{ color: '#fff', fontSize: 13, fontWeight: '500' }}>Tap to retry</Text>
          </TouchableOpacity>
        )}

        <Text style={{
          fontSize: 12,
          color: 'rgba(255,255,255,0.50)',
          marginTop: 12,
          textAlign: 'center',
          letterSpacing: 0.3,
        }}>
          {statusMessage}
        </Text>
      </Animated.View>

      {/* Footer */}
      <View style={{
        position: 'absolute', bottom: 40,
        alignItems: 'center', gap: 8,
      }}>
        <Text style={{
          color: 'rgba(255,255,255,0.45)',
          fontSize: 11,
          letterSpacing: 0.3,
        }}>
          DepEd Division of Leyte
        </Text>

        <View style={{ flexDirection: 'row' }}>
          <View style={{ width: 28, height: 4, backgroundColor: '#0038A8', borderWidth: 1, borderColor: 'rgba(255,255,255,0.3)', borderRadius: 1 }} />
          <View style={{ width: 28, height: 4, backgroundColor: '#CE1126' }} />
          <View style={{ width: 28, height: 4, backgroundColor: '#FCD116', borderRadius: 1 }} />
        </View>
      </View>
    </Animated.View>
  );
}

function LoadingDot({ delay }: { delay: number }) {
  const anim = useRef(new Animated.Value(0.25)).current;

  useEffect(() => {
    const t = setTimeout(() => {
      Animated.loop(
        Animated.sequence([
          Animated.timing(anim, { toValue: 1,    duration: 400, useNativeDriver: true }),
          Animated.timing(anim, { toValue: 0.25, duration: 400, useNativeDriver: true }),
        ])
      ).start();
    }, delay);
    return () => clearTimeout(t);
  }, []);

  return (
    <Animated.View style={{
      width: 8, height: 8, borderRadius: 4,
      backgroundColor: '#FCD116',
      opacity: anim,
    }} />
  );
}