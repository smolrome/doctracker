import { useEffect, useState } from 'react';
import { Tabs } from 'expo-router';
import { useRouter } from 'expo-router';
import { View, TouchableOpacity, Modal, Text, TextInput, ScrollView } from 'react-native';
import { useAuthStore } from '../../lib/store';
import { FileText, QrCode, LayoutDashboard, User, Plus, X } from 'lucide-react-native';
import { KeyboardAvoidingView, Platform } from 'react-native';

const label: any = {
  fontSize: 13,
  fontWeight: '600',
  color: '#475569',
  marginBottom: 6,
};

const req: any = {
  color: '#EF4444',
};

const input: any = {
  backgroundColor: '#F8FAFC',
  borderRadius: 10,
  padding: 12,
  marginBottom: 14,
  borderWidth: 1,
  borderColor: '#E2E8F0',
  fontSize: 14,
  color: '#1E293B',
};

export default function AppLayout() {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuthStore();
  const [modalVisible, setModalVisible] = useState(false);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace('/(auth)/login');
    }
  }, [isAuthenticated, isLoading]);

  return (
    <>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: '#0038A8',
          tabBarInactiveTintColor: '#64748B',
          tabBarStyle: {
            position: 'absolute',
            bottom: 30,
            left: 20,
            right: 20,
            height: 64,
            borderRadius: 32,
            backgroundColor: '#FFFFFF',
            borderTopWidth: 0,
            elevation: 8,
            shadowColor: '#0038A8',
            shadowOffset: { width: 0, height: 4 },
            shadowOpacity: 0.15,
            shadowRadius: 12,
            paddingBottom: 0,
            paddingHorizontal: 8,
            overflow: 'visible',
          },
          tabBarLabelStyle: {
            fontSize: 11,
            fontWeight: '600',
            marginTop: -2,
          },
          tabBarItemStyle: {
            paddingVertical: 4,
          },
        }}
      >
        <Tabs.Screen
          name="dashboard"
          options={{
            title: 'Dashboard',
            tabBarIcon: ({ color }) => <LayoutDashboard size={22} color={color} />,
          }}
        />
        <Tabs.Screen
          name="documents/index"
          options={{
            title: 'Documents',
            tabBarIcon: ({ color }) => <FileText size={22} color={color} />,
          }}
        />
        <Tabs.Screen
          name="add"
          options={{
            title: '',
            tabBarButton: () => (
              <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
                <TouchableOpacity
                  onPress={() => setModalVisible(true)}
                  style={{
                    position: 'absolute',
                    top: -28,
                    width: 56,
                    height: 56,
                    borderRadius: 28,
                    backgroundColor: '#10B981',
                    alignItems: 'center',
                    justifyContent: 'center',
                    shadowColor: '#10B981',
                    shadowOffset: { width: 0, height: 6 },
                    shadowOpacity: 0.5,
                    shadowRadius: 10,
                    elevation: 10,
                    borderWidth: 3,
                    borderColor: '#FFFFFF',
                  }}
                >
                  <Plus size={28} color="#fff" />
                </TouchableOpacity>
              </View>
            ),
          }}
        />
        <Tabs.Screen
          name="scanner"
          options={{
            title: 'Scan',
            tabBarIcon: ({ color }) => <QrCode size={22} color={color} />,
          }}
        />
        <Tabs.Screen
          name="profile"
          options={{
            title: 'Profile',
            tabBarIcon: ({ color }) => <User size={22} color={color} />,
          }}
        />
        <Tabs.Screen name="index" options={{ href: null }} />
        <Tabs.Screen name="documents/[id]" options={{ href: null }} />
        <Tabs.Screen name="documents/new" options={{ href: null }} />
        <Tabs.Screen name="notifications" options={{ href: null }} />
      </Tabs>

      <Modal
        visible={modalVisible}
        animationType="fade"
        transparent={true}
        onRequestClose={() => setModalVisible(false)}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={{ flex: 1 }}
        >
          <View style={{
            flex: 1,
            backgroundColor: 'rgba(0,0,0,0.5)',
            justifyContent: 'center',
            alignItems: 'center',
            paddingHorizontal: 20,
          }}>
            <TouchableOpacity
              style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
              onPress={() => setModalVisible(false)}
              activeOpacity={1}
            />

            <View style={{
              backgroundColor: '#FFFFFF',
              borderRadius: 24,
              width: '100%',
              maxHeight: '85%',
              shadowColor: '#000',
              shadowOffset: { width: 0, height: 8 },
              shadowOpacity: 0.2,
              shadowRadius: 24,
              elevation: 16,
            }}>
              <View style={{
                flexDirection: 'row',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: 20,
                borderBottomWidth: 1,
                borderBottomColor: '#F1F5F9',
              }}>
                <Text style={{ fontSize: 18, fontWeight: '800', color: '#0038A8' }}>
                  ➕ New Document
                </Text>
                <TouchableOpacity onPress={() => setModalVisible(false)}>
                  <X size={22} color="#94A3B8" />
                </TouchableOpacity>
              </View>

              <ScrollView
                contentContainerStyle={{ padding: 20, paddingBottom: 8 }}
                showsVerticalScrollIndicator={false}
                keyboardShouldPersistTaps="handled"
                keyboardDismissMode="interactive"
              >
                <Text style={label}>Unit / Office / School <Text style={req}>*</Text></Text>
                <TextInput placeholder="e.g. Palo Central School" style={input} placeholderTextColor="#CBD5E1" />

                <Text style={label}>Sender Name & Designation</Text>
                <TextInput placeholder="e.g. Juan dela Cruz, Principal II" style={input} placeholderTextColor="#CBD5E1" />

                <Text style={label}>Content / Particulars <Text style={req}>*</Text></Text>
                <TextInput placeholder="e.g. Plantilla of Personnel" style={input} placeholderTextColor="#CBD5E1" />

                <Text style={label}>Document Type</Text>
                <TextInput placeholder="Select or type document type" style={input} placeholderTextColor="#CBD5E1" />

                <Text style={label}>Referred To</Text>
                <TextInput placeholder="e.g. SDS, Budget Officer" style={input} placeholderTextColor="#CBD5E1" />

                <Text style={label}>Description / Remarks</Text>
                <TextInput
                  placeholder="Additional details..."
                  style={[input, { height: 80, textAlignVertical: 'top' }]}
                  multiline
                  placeholderTextColor="#CBD5E1"
                />
              </ScrollView>

              <View style={{ padding: 16, paddingTop: 8, borderTopWidth: 1, borderTopColor: '#F1F5F9' }}>
                <TouchableOpacity style={{
                  backgroundColor: '#10B981',
                  borderRadius: 12,
                  paddingVertical: 14,
                  alignItems: 'center',
                }}>
                  <Text style={{ color: '#fff', fontSize: 15, fontWeight: '700' }}>➕ Add to Log List</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </>
  );
}