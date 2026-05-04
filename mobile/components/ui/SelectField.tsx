import { useState } from 'react';
import {
  Modal,
  View,
  Text,
  TextInput,
  FlatList,
  TouchableOpacity,
  StatusBar,
} from 'react-native';
import { Search, X, ChevronDown, Check, CornerDownLeft } from 'lucide-react-native';

interface Props {
  value: string;
  onChange: (val: string) => void;
  options: string[];
  placeholder?: string;
  label?: string;
  disabled?: boolean;
  allowFreeText?: boolean;
}

export function SelectField({
  value,
  onChange,
  options,
  placeholder = 'Select…',
  label = 'Select',
  disabled = false,
  allowFreeText = false,
}: Props) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');

  const trimmed = search.trim();
  const filtered = trimmed
    ? options.filter((o) => o.toLowerCase().includes(trimmed.toLowerCase()))
    : options;

  // When allowFreeText and the typed text isn't already an exact option, show a
  // "Use '[text]'" row at the top so the user can confirm a manually typed value.
  const showFreeTextRow =
    allowFreeText &&
    trimmed.length > 0 &&
    !options.some((o) => o.toLowerCase() === trimmed.toLowerCase());

  const handleSelect = (item: string) => {
    onChange(item);
    setSearch('');
    setOpen(false);
  };

  const handleClose = () => {
    setSearch('');
    setOpen(false);
  };

  return (
    <>
      {/* Trigger button */}
      <TouchableOpacity
        onPress={() => !disabled && setOpen(true)}
        activeOpacity={0.7}
        style={{
          backgroundColor: '#fff',
          borderRadius: 12,
          paddingHorizontal: 14,
          paddingVertical: 13,
          marginBottom: 16,
          borderWidth: 1.5,
          borderColor: '#E2E8F0',
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          opacity: disabled ? 0.5 : 1,
        }}
      >
        <Text style={{ fontSize: 14.5, color: value ? '#1E293B' : '#CBD5E1', flex: 1 }}>
          {value || placeholder}
        </Text>
        <ChevronDown size={16} color="#94A3B8" />
      </TouchableOpacity>

      {/* Picker modal */}
      <Modal visible={open} animationType="slide" onRequestClose={handleClose}>
        <StatusBar barStyle="light-content" backgroundColor="#0038A8" />
        <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>

          {/* Header */}
          <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 16, paddingHorizontal: 20 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <Text style={{ color: '#fff', fontSize: 18, fontWeight: '800' }}>{label}</Text>
              <TouchableOpacity onPress={handleClose} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
                <X size={22} color="#fff" />
              </TouchableOpacity>
            </View>

            {/* Search bar */}
            <View style={{
              flexDirection: 'row', alignItems: 'center',
              backgroundColor: 'rgba(255,255,255,0.15)',
              borderRadius: 12, paddingHorizontal: 12,
              borderWidth: 1, borderColor: 'rgba(255,255,255,0.20)',
            }}>
              <Search size={15} color="rgba(255,255,255,0.60)" />
              <TextInput
                value={search}
                onChangeText={setSearch}
                placeholder={allowFreeText ? 'Search or type a name…' : 'Search…'}
                placeholderTextColor="rgba(255,255,255,0.45)"
                style={{ flex: 1, color: '#fff', fontSize: 14, paddingVertical: 10, marginLeft: 8 }}
                autoFocus
                returnKeyType={allowFreeText ? 'done' : 'search'}
                onSubmitEditing={() => {
                  if (allowFreeText && trimmed) handleSelect(trimmed);
                }}
              />
              {search.length > 0 && (
                <TouchableOpacity onPress={() => setSearch('')}>
                  <X size={14} color="rgba(255,255,255,0.60)" />
                </TouchableOpacity>
              )}
            </View>
          </View>

          {/* Options list */}
          <FlatList
            data={filtered}
            keyExtractor={(item) => item}
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={{ paddingBottom: 40 }}
            ListHeaderComponent={
              showFreeTextRow ? (
                <TouchableOpacity
                  onPress={() => handleSelect(trimmed)}
                  activeOpacity={0.7}
                  style={{
                    flexDirection: 'row', alignItems: 'center',
                    paddingVertical: 14, paddingHorizontal: 20,
                    borderBottomWidth: 0.5, borderBottomColor: '#E2E8F0',
                    backgroundColor: '#EFF6FF', gap: 10,
                  }}
                >
                  <CornerDownLeft size={15} color="#0038A8" />
                  <Text style={{ flex: 1, fontSize: 14.5, color: '#0038A8', fontWeight: '600' }}>
                    Use &quot;{trimmed}&quot;
                  </Text>
                </TouchableOpacity>
              ) : null
            }
            ListEmptyComponent={
              !showFreeTextRow ? (
                <View style={{ alignItems: 'center', paddingTop: 48 }}>
                  <Text style={{ color: '#94A3B8', fontSize: 14 }}>
                    {allowFreeText ? 'Type a name above to enter manually' : 'No options found'}
                  </Text>
                </View>
              ) : null
            }
            renderItem={({ item }) => {
              const selected = item === value;
              return (
                <TouchableOpacity
                  onPress={() => handleSelect(item)}
                  activeOpacity={0.7}
                  style={{
                    flexDirection: 'row', alignItems: 'center',
                    paddingVertical: 14, paddingHorizontal: 20,
                    borderBottomWidth: 0.5, borderBottomColor: '#E2E8F0',
                    backgroundColor: selected ? '#EFF6FF' : '#fff',
                  }}
                >
                  <Text style={{
                    flex: 1, fontSize: 14.5,
                    color: selected ? '#0038A8' : '#1E293B',
                    fontWeight: selected ? '700' : '400',
                  }}>
                    {item}
                  </Text>
                  {selected && <Check size={18} color="#0038A8" />}
                </TouchableOpacity>
              );
            }}
          />
        </View>
      </Modal>
    </>
  );
}
