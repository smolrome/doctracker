import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
} from 'react-native';
import { useRouter } from 'expo-router';
import * as Notifications from 'expo-notifications';
import { useState, useEffect } from 'react';

export default function NotificationsScreen() {
  const router = useRouter();
  const [notifications, setNotifications] = useState<any[]>([]);

  useEffect(() => {
    Notifications.getPresentedNotificationsAsync().then((notifs) => {
      setNotifications(notifs);
    });
  }, []);

  return (
    <View style={{ flex: 1, backgroundColor: '#F3F4F6' }}>
      <View style={{
        backgroundColor: '#0038A8',
        paddingTop: 56,
        paddingBottom: 20,
        paddingHorizontal: 16,
      }}>
        <Text style={{ color: '#fff', fontSize: 20, fontWeight: 'bold' }}>
          Notifications
        </Text>
      </View>

      <FlatList
        data={notifications}
        keyExtractor={(_, i) => String(i)}
        contentContainerStyle={{ padding: 16 }}
        ListEmptyComponent={
          <View style={{ alignItems: 'center', paddingTop: 80 }}>
            <Text style={{ fontSize: 40 }}>🔔</Text>
            <Text style={{ color: '#9CA3AF', marginTop: 12, fontSize: 15 }}>
              No notifications yet
            </Text>
            <Text style={{ color: '#9CA3AF', fontSize: 13, marginTop: 4 }}>
              You'll be notified when documents are updated
            </Text>
          </View>
        }
        renderItem={({ item }) => (
          <TouchableOpacity
            onPress={() => {
              const docId = item.request.content.data?.doc_id;
              if (docId) router.push(`/(app)/documents/${docId}`);
            }}
            style={{
              backgroundColor: '#fff',
              borderRadius: 12,
              padding: 14,
              marginBottom: 10,
            }}
          >
            <Text style={{ fontWeight: '600', color: '#111', fontSize: 14 }}>
              {item.request.content.title}
            </Text>
            <Text style={{ color: '#6B7280', fontSize: 13, marginTop: 4 }}>
              {item.request.content.body}
            </Text>
          </TouchableOpacity>
        )}
      />
    </View>
  );
}