import * as Device from 'expo-device';
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import api from './api';

export async function registerForPushNotifications(): Promise<string | null> {
  if (Constants.appOwnership === 'expo') return null;

  const Notifications = require('expo-notifications');

  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: true,
      shouldSetBadge: true,
    }),
  });

  if (!Device.isDevice) {
    console.log('Push notifications require a physical device');
    return null;
  }

  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;

  if (existingStatus !== 'granted') {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  if (finalStatus !== 'granted') {
    console.log('Push notification permission denied');
    return null;
  }

  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('documents', {
      name: 'Document Updates',
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#0038A8',
      sound: 'default',
    });

    await Notifications.setNotificationChannelAsync('system', {
      name: 'System Alerts',
      importance: Notifications.AndroidImportance.DEFAULT,
      sound: 'default',
    });
  }

  try {
    const projectId = Constants.expoConfig?.extra?.eas?.projectId
      ?? Constants.easConfig?.projectId;

    const tokenData = await Notifications.getExpoPushTokenAsync({ projectId });
    const token = tokenData.data;

    console.log('Push token:', token);

    await registerTokenWithBackend(token);

    return token;
  } catch (err) {
    console.error('Failed to get push token:', err);
    return null;
  }
}

async function registerTokenWithBackend(token: string) {
  try {
    await api.post('/notifications/register-token', { token });
    console.log('Token registered with backend');
  } catch (err) {
    console.error('Failed to register token:', err);
  }
}

export function useNotificationListeners(
  onReceive?: (notification: any) => void,
  onResponse?: (response: any) => void
) {
  return { onReceive, onResponse };
}
