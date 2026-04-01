import { View, Text } from 'react-native';

export default function Scanner() {
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
      <Text style={{ fontSize: 20, color: '#0038A8' }}>QR Scanner</Text>
    </View>
  );
}