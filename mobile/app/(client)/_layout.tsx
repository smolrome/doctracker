import { useEffect } from 'react';
import { Tabs } from 'expo-router';
import { useRouter } from 'expo-router';
import { FileText, PlusCircle, ScanLine, Trash2, User } from 'lucide-react-native';
import { useAuthStore } from '../../lib/store';

export default function ClientLayout() {
  const router = useRouter();
  const { isAuthenticated, isLoading, user } = useAuthStore();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace('/(auth)/login');
    }
    // Redirect non-clients (staff/admin) back to app route
    if (!isLoading && isAuthenticated && user?.role !== 'client') {
      router.replace('/(app)/dashboard');
    }
  }, [isAuthenticated, isLoading, user]);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: '#0038A8',
        tabBarInactiveTintColor: '#94A3B8',
        tabBarStyle: {
          height: 62,
          backgroundColor: '#FFFFFF',
          borderTopWidth: 0.5,
          borderTopColor: '#E2E8F0',
          elevation: 8,
          shadowColor: '#0038A8',
          shadowOffset: { width: 0, height: -2 },
          shadowOpacity: 0.08,
          shadowRadius: 8,
        },
        tabBarLabelStyle: { fontSize: 10.5, fontWeight: '700', marginBottom: 4 },
        tabBarItemStyle: { paddingVertical: 4 },
      }}
    >
      <Tabs.Screen
        name="my-docs"
        options={{ title: 'My Docs', tabBarIcon: ({ color }) => <FileText size={22} color={color} /> }}
      />
      <Tabs.Screen
        name="submit"
        options={{ title: 'Submit', tabBarIcon: ({ color }) => <PlusCircle size={22} color={color} /> }}
      />
      <Tabs.Screen
        name="scan"
        options={{ title: 'Scan QR', tabBarIcon: ({ color }) => <ScanLine size={22} color={color} /> }}
      />
      <Tabs.Screen
        name="trash"
        options={{ title: 'Trash', tabBarIcon: ({ color }) => <Trash2 size={22} color={color} /> }}
      />
      <Tabs.Screen
        name="profile"
        options={{ title: 'Profile', tabBarIcon: ({ color }) => <User size={22} color={color} /> }}
      />
      <Tabs.Screen name="track/[id]" options={{ href: null }} />
      <Tabs.Screen name="my-qr" options={{ href: null }} />
    </Tabs>
  );
}
