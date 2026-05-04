import { useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, Alert,
  TextInput, ActivityIndicator, StatusBar, Modal,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Settings, Plus, X, RotateCcw, ChevronDown, ChevronUp } from 'lucide-react-native';
import api from '../../lib/api';

type DropdownConfig = {
  field_name: string;
  display_name: string;
  options: string[];
  is_default: boolean;
};

export default function DropdownOptions() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [expandedField, setExpandedField] = useState<string | null>(null);
  const [editModal, setEditModal] = useState(false);
  const [editingField, setEditingField] = useState<DropdownConfig | null>(null);
  const [newOption, setNewOption] = useState('');
  const [editOptions, setEditOptions] = useState<string[]>([]);

  // ── Data ──────────────────────────────────────────────────────────────────

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['dropdown-options'],
    queryFn: async () => {
      const res = await api.get('/dropdown-options/admin');
      return res.data as Record<string, DropdownConfig>;
    },
    staleTime: 1000 * 60 * 5,
  });

  // Normalise: ensure every config has an options array (API may return null for empty fields)
  const configs = data
    ? Object.values(data).map((c: any) => ({ ...c, options: Array.isArray(c.options) ? c.options : [] }))
    : [];

  // ── Mutations ─────────────────────────────────────────────────────────────

  const saveMutation = useMutation({
    mutationFn: ({ field, options }: { field: string; options: string[] }) =>
      api.put(`/dropdown-options/${field}`, { options }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dropdown-options'] });
      queryClient.invalidateQueries({ queryKey: ['dropdown-configs'] });
      setEditModal(false);
      Alert.alert('Saved', 'Dropdown options updated successfully.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to save.'),
  });

  const resetMutation = useMutation({
    mutationFn: (field: string) => api.delete(`/dropdown-options/${field}/reset`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dropdown-options'] });
      queryClient.invalidateQueries({ queryKey: ['dropdown-configs'] });
      Alert.alert('Reset', 'Options restored to defaults.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Cannot reset this field.'),
  });

  // ── Handlers ─────────────────────────────────────────────────────────────

  const openEdit = (config: DropdownConfig) => {
    setEditingField(config);
    setEditOptions([...(config.options ?? [])]);
    setNewOption('');
    setEditModal(true);
  };

  const addOption = () => {
    const trimmed = newOption.trim();
    if (!trimmed) return;
    if (editOptions.includes(trimmed)) {
      Alert.alert('Duplicate', 'This option already exists.');
      return;
    }
    setEditOptions((prev) => [...prev, trimmed]);
    setNewOption('');
  };

  const removeOption = (idx: number) => {
    if (editOptions.length <= 1) {
      Alert.alert('Error', 'At least one option is required.');
      return;
    }
    setEditOptions((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSave = () => {
    if (!editingField) return;
    if (editOptions.length === 0) {
      Alert.alert('Error', 'Options cannot be empty.');
      return;
    }
    saveMutation.mutate({ field: editingField.field_name, options: editOptions });
  };

  const handleReset = (config: DropdownConfig) => {
    Alert.alert(
      'Reset to Default',
      `Reset "${config.display_name}" options back to defaults? Your custom options will be lost.`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Reset', style: 'destructive', onPress: () => resetMutation.mutate(config.field_name) },
      ],
    );
  };

  // ── Screen ─────────────────────────────────────────────────────────────────

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
      <StatusBar barStyle="light-content" backgroundColor="#1E3A5F" />

      {/* Header */}
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 }}>
        <TouchableOpacity
          onPress={() => router.back()}
          style={{ marginBottom: 14, flexDirection: 'row', alignItems: 'center', gap: 6 }}
        >
          <ArrowLeft size={18} color="rgba(255,255,255,0.70)" />
          <Text style={{ color: 'rgba(255,255,255,0.70)', fontSize: 14, fontWeight: '600' }}>Back</Text>
        </TouchableOpacity>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Settings size={20} color="#fff" />
          <Text style={{ color: '#fff', fontSize: 22, fontWeight: '800', letterSpacing: -0.4 }}>
            Dropdown Options
          </Text>
        </View>
        <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 13, marginTop: 4 }}>
          Manage custom values for document fields
        </Text>
      </View>

      {isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator size="large" color="#0038A8" />
          <Text style={{ color: '#94A3B8', marginTop: 12, fontSize: 13 }}>Loading options…</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }}>
          {configs.map((config, idx) => {
            const expanded = expandedField === config.field_name;
            return (
              <View key={config.field_name ?? String(idx)} style={{
                backgroundColor: '#fff',
                borderRadius: 14,
                marginBottom: 12,
                borderWidth: 0.5,
                borderColor: '#E2E8F0',
                overflow: 'hidden',
              }}>
                {/* Header row */}
                <TouchableOpacity
                  onPress={() => setExpandedField(expanded ? null : config.field_name)}
                  style={{
                    flexDirection: 'row', alignItems: 'center',
                    padding: 16, gap: 10,
                  }}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 14 }}>
                      {config.display_name}
                    </Text>
                    <Text style={{ color: '#64748B', fontSize: 12, marginTop: 2 }}>
                      {config.options.length} option{config.options.length !== 1 ? 's' : ''} ·{' '}
                      <Text style={{ color: config.is_default ? '#16A34A' : '#0038A8' }}>
                        {config.is_default ? 'Default' : 'Custom'}
                      </Text>
                    </Text>
                  </View>
                  {expanded ? (
                    <ChevronUp size={18} color="#94A3B8" />
                  ) : (
                    <ChevronDown size={18} color="#94A3B8" />
                  )}
                </TouchableOpacity>

                {/* Expanded content */}
                {expanded && (
                  <View style={{ paddingHorizontal: 16, paddingBottom: 16 }}>
                    {/* Option pills */}
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
                      {config.options.map((opt, oi) => (
                        <View key={`${config.field_name}-opt-${oi}`} style={{
                          backgroundColor: '#EFF6FF',
                          borderRadius: 20, paddingHorizontal: 10, paddingVertical: 4,
                          borderWidth: 1, borderColor: '#BFDBFE',
                        }}>
                          <Text style={{ color: '#1E40AF', fontSize: 12, fontWeight: '600' }}>{opt}</Text>
                        </View>
                      ))}
                    </View>

                    {/* Action buttons */}
                    <View style={{ flexDirection: 'row', gap: 10 }}>
                      <TouchableOpacity
                        onPress={() => openEdit(config)}
                        style={{
                          flex: 1, backgroundColor: '#EFF6FF',
                          borderRadius: 10, paddingVertical: 10,
                          alignItems: 'center', justifyContent: 'center',
                          borderWidth: 1, borderColor: '#BFDBFE',
                          flexDirection: 'row', gap: 6,
                        }}
                      >
                        <Settings size={14} color="#1E40AF" />
                        <Text style={{ color: '#1E40AF', fontWeight: '700', fontSize: 13 }}>Edit Options</Text>
                      </TouchableOpacity>

                      <TouchableOpacity
                        onPress={() => handleReset(config)}
                        disabled={config.is_default || resetMutation.isPending}
                        style={{
                          flex: 1, backgroundColor: config.is_default ? '#F8FAFC' : '#FFFBEB',
                          borderRadius: 10, paddingVertical: 10,
                          alignItems: 'center', justifyContent: 'center',
                          borderWidth: 1, borderColor: config.is_default ? '#E2E8F0' : '#FDE68A',
                          flexDirection: 'row', gap: 6,
                        }}
                      >
                        <RotateCcw size={14} color={config.is_default ? '#CBD5E1' : '#B45309'} />
                        <Text style={{
                          color: config.is_default ? '#CBD5E1' : '#B45309',
                          fontWeight: '700', fontSize: 13,
                        }}>Reset</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                )}
              </View>
            );
          })}
        </ScrollView>
      )}

      {/* Edit Modal */}
      <Modal visible={editModal} animationType="slide" presentationStyle="pageSheet">
        <KeyboardAvoidingView
          style={{ flex: 1, backgroundColor: '#F8FAFC' }}
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        >
          {/* Modal Header */}
          <View style={{
            backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20,
            paddingHorizontal: 20, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <View>
              <Text style={{ color: '#fff', fontSize: 18, fontWeight: '800' }}>
                Edit Options
              </Text>
              <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 13, marginTop: 2 }}>
                {editingField?.display_name}
              </Text>
            </View>
            <TouchableOpacity onPress={() => setEditModal(false)}>
              <X size={22} color="#fff" />
            </TouchableOpacity>
          </View>

          <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }}>
            {/* Add option row */}
            <View style={{
              flexDirection: 'row', gap: 8, marginBottom: 20,
              backgroundColor: '#fff', borderRadius: 12, padding: 12,
              borderWidth: 1, borderColor: '#E2E8F0',
            }}>
              <TextInput
                value={newOption}
                onChangeText={setNewOption}
                onSubmitEditing={addOption}
                placeholder="Add new option…"
                placeholderTextColor="#94A3B8"
                style={{ flex: 1, fontSize: 14, color: '#1E293B', paddingVertical: 4 }}
              />
              <TouchableOpacity
                onPress={addOption}
                style={{
                  backgroundColor: '#0038A8', borderRadius: 8,
                  paddingHorizontal: 14, paddingVertical: 8,
                  flexDirection: 'row', alignItems: 'center', gap: 4,
                }}
              >
                <Plus size={14} color="#fff" />
                <Text style={{ color: '#fff', fontWeight: '700', fontSize: 13 }}>Add</Text>
              </TouchableOpacity>
            </View>

            {/* Option list */}
            <Text style={{
              fontSize: 11, fontWeight: '700', color: '#64748B',
              textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 10,
            }}>
              Options ({editOptions.length})
            </Text>

            {editOptions.map((opt, idx) => (
              <View key={`${opt}-${idx}`} style={{
                backgroundColor: '#fff', borderRadius: 10,
                paddingHorizontal: 14, paddingVertical: 12,
                marginBottom: 8, flexDirection: 'row', alignItems: 'center',
                borderWidth: 0.5, borderColor: '#E2E8F0',
              }}>
                <Text style={{ flex: 1, color: '#1E293B', fontSize: 14 }}>{opt}</Text>
                <TouchableOpacity onPress={() => removeOption(idx)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                  <X size={16} color="#EF4444" />
                </TouchableOpacity>
              </View>
            ))}
          </ScrollView>

          {/* Save button */}
          <View style={{ padding: 16, borderTopWidth: 0.5, borderTopColor: '#E2E8F0', backgroundColor: '#fff' }}>
            <TouchableOpacity
              onPress={handleSave}
              disabled={saveMutation.isPending}
              style={{
                backgroundColor: saveMutation.isPending ? '#93C5FD' : '#0038A8',
                borderRadius: 13, paddingVertical: 15, alignItems: 'center',
              }}
            >
              <Text style={{ color: '#fff', fontWeight: '800', fontSize: 15 }}>
                {saveMutation.isPending ? 'Saving…' : 'Save Changes'}
              </Text>
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}
