import { View, Text } from 'react-native';

export default function NewDocument() {
  return (
    <View style={{ flex: 1, backgroundColor: '#F3F4F6' }}>
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 16 }}>
        <Text style={{ color: '#fff', fontSize: 20, fontWeight: 'bold' }}>New Document</Text>
      </View>
    </View>
  );
}