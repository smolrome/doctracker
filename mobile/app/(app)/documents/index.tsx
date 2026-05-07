import { useState, useMemo } from 'react';
import {
  View,
  Text,
  FlatList,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  StatusBar,
  Dimensions,
  Modal,
  Alert,
  ScrollView,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Search, CheckSquare, Square, X, Trash2, RefreshCw, UserCheck, Users, Filter, Download } from 'lucide-react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { useDocuments } from '../../../hooks/useDocuments';
import { useNetwork } from '../../../hooks/useNetwork';
import { OfflineBanner } from '../../../components/ui/OfflineBanner';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../../../lib/store';
import { useStaff, useOffices, useDropdownOptions } from '../../../hooks/useDropdownOptions';
import api from '../../../lib/api';

const { width } = Dimensions.get('window');

// Status badge config — semantic bg/text pairs (matches Dashboard)
const STATUS_CONFIG: Record<string, { bg: string; text: string; accent: string }> = {
  pending:    { bg: '#FEF3C7', text: '#B45309', accent: '#F59E0B' },
  received:   { bg: '#DBEAFE', text: '#1E40AF', accent: '#3B82F6' },
  released:   { bg: '#D1FAE5', text: '#065F46', accent: '#10B981' },
  routed:     { bg: '#EDE9FE', text: '#5B21B6', accent: '#8B5CF6' },
  'in review':{ bg: '#E0E7FF', text: '#3730A3', accent: '#6366F1' },
  transferred:{ bg: '#CFFAFE', text: '#155E75', accent: '#06B6D4' },
  'on hold':  { bg: '#FEE2E2', text: '#991B1B', accent: '#EF4444' },
};

const ALL_STATUSES = ['Pending', 'Received', 'Released', 'Routed', 'In Review', 'Transferred', 'On Hold', 'Returned', 'Archived'];

function getStatus(status: string) {
  const key = status?.toLowerCase();
  return STATUS_CONFIG[key] ?? { bg: '#F1F5F9', text: '#475569', accent: '#94A3B8' };
}

const STATUS_FILTERS = ['All', 'Pending', 'Received', 'Released', 'Routed', 'On Hold', 'In Review', 'Transferred', 'Returned', 'Archived'];

export default function Documents() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin';

  const [search, setSearch] = useState('');
  const [activeFilter, setActiveFilter] = useState('All');
  const [searchInput, setSearchInput] = useState('');
  const { isOnline } = useNetwork();

  // ── Select state ───────────────────────────────────────────────────────────
  const [isSelecting, setIsSelecting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // ── Bulk status modal state ────────────────────────────────────────────────
  const [bulkStatusModal, setBulkStatusModal] = useState(false);
  const [bulkRemarks, setBulkRemarks] = useState('');
  const [selectedBulkStatus, setSelectedBulkStatus] = useState<string | null>(null);

  // ── Assign modal state ─────────────────────────────────────────────────────
  const [assignModal, setAssignModal] = useState(false);
  const [staffSearch, setStaffSearch] = useState('');
  const [selectedStaff, setSelectedStaff] = useState<string | null>(null);

  // ── Delete All Unassigned modal state ──────────────────────────────────────
  const [deleteAllModal, setDeleteAllModal] = useState(false);
  const [deleteAllConfirmText, setDeleteAllConfirmText] = useState('');

  // ── Advanced filter state ──────────────────────────────────────────────────
  const [showFilterPanel, setShowFilterPanel] = useState(false);
  const [filterOffice, setFilterOffice] = useState('');
  const [filterCat, setFilterCat] = useState('');
  const [filterStaff, setFilterStaff] = useState('');
  const [filterSource, setFilterSource] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');
  const [pickerModal, setPickerModal] = useState<'office' | 'category' | 'staff' | null>(null);
  const [pickerSearch, setPickerSearch] = useState('');

  const activeFilterCount = [filterOffice, filterCat, filterStaff, filterSource, filterDateFrom, filterDateTo].filter(Boolean).length;

  const [isExporting, setIsExporting] = useState(false);

  const { data, isLoading, isRefetching, refetch, isFromCache } = useDocuments(
    search,
    activeFilter,
    {
      office: filterOffice || undefined,
      cat: filterCat || undefined,
      staff: filterStaff || undefined,
      source: filterSource || undefined,
      date_from: filterDateFrom || undefined,
      date_to: filterDateTo || undefined,
    }
  );
  const docs = data?.documents ?? [];

  const { data: staffList = [] } = useStaff();
  const { data: offices = [] } = useOffices();
  const { data: dropdownOptions = {} } = useDropdownOptions();
  const categoryOptions: string[] = (dropdownOptions as Record<string, string[]>)['category'] ?? [];

  const filterStaffLabel = filterStaff
    ? (staffList.find((s) => s.username === filterStaff)?.full_name || filterStaff)
    : '';

  const pickerOptions = useMemo(() => {
    if (pickerModal === 'office') return offices.map((o) => o.office_name);
    if (pickerModal === 'category') return categoryOptions;
    if (pickerModal === 'staff') return staffList.map((s) => s.full_name).filter(Boolean);
    return [];
  }, [pickerModal, offices, categoryOptions, staffList]);

  const filteredPickerOptions = pickerSearch
    ? pickerOptions.filter((o) => o.toLowerCase().includes(pickerSearch.toLowerCase()))
    : pickerOptions;

  const pickerLabel =
    pickerModal === 'office' ? 'Office' :
    pickerModal === 'category' ? 'Category' : 'Staff Member';

  const currentPickerValue =
    pickerModal === 'staff' ? filterStaffLabel :
    pickerModal === 'office' ? filterOffice :
    pickerModal === 'category' ? filterCat : '';

  const applyPickerValue = (value: string) => {
    if (pickerModal === 'office') setFilterOffice(value);
    else if (pickerModal === 'category') setFilterCat(value);
    else if (pickerModal === 'staff') {
      const s = staffList.find((st) => st.full_name === value);
      setFilterStaff(s?.username || value);
    }
    setPickerModal(null);
    setPickerSearch('');
  };

  const clearPickerValue = () => {
    if (pickerModal === 'office') setFilterOffice('');
    else if (pickerModal === 'category') setFilterCat('');
    else if (pickerModal === 'staff') setFilterStaff('');
    setPickerModal(null);
    setPickerSearch('');
  };

  const clearAllFilters = () => {
    setFilterOffice('');
    setFilterCat('');
    setFilterStaff('');
    setFilterSource('');
    setFilterDateFrom('');
    setFilterDateTo('');
  };

  const handleSearch = () => setSearch(searchInput);

  const doExport = async (params: Record<string, string | undefined>) => {
    setIsExporting(true);
    try {
      const res = await api.get('/export-csv', { params, responseType: 'text' });
      const csvContent = typeof res.data === 'string' ? res.data : JSON.stringify(res.data);
      const today = new Date().toISOString().slice(0, 10);
      const filename = `documents_export_${today}.csv`;
      const fileUri = (FileSystem.cacheDirectory ?? '') + filename;
      await FileSystem.writeAsStringAsync(fileUri, csvContent, { encoding: 'utf8' });
      const canShare = await Sharing.isAvailableAsync();
      if (canShare) {
        await Sharing.shareAsync(fileUri, { mimeType: 'text/csv', dialogTitle: 'Export Documents CSV' });
      } else {
        Alert.alert('Saved', `File saved to: ${fileUri}`);
      }
    } catch (e: any) {
      Alert.alert('Export Failed', e?.response?.data?.error || e?.message || 'Could not export CSV.');
    } finally {
      setIsExporting(false);
    }
  };

  const handleExport = () => {
    Alert.alert('Export CSV', 'Choose what to export:', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Export All', onPress: () => doExport({}) },
      {
        text: 'Export Current Filters',
        onPress: () => doExport({
          search: search || undefined,
          status: activeFilter !== 'All' ? activeFilter : undefined,
          office: filterOffice || undefined,
          cat: filterCat || undefined,
          staff: filterStaff || undefined,
          source: filterSource || undefined,
          date_from: filterDateFrom || undefined,
          date_to: filterDateTo || undefined,
        }),
      },
    ]);
  };

  // ── Mutations ──────────────────────────────────────────────────────────────

  const bulkStatusMutation = useMutation({
    mutationFn: ({ status, remarks }: { status: string; remarks: string }) =>
      api.post('/documents/bulk-status', { doc_ids: Array.from(selectedIds), status, remarks }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      setBulkStatusModal(false);
      setSelectedBulkStatus(null);
      setSelectedIds(new Set());
      setIsSelecting(false);
      setBulkRemarks('');
      Alert.alert('Updated', res.data?.message || `${selectedIds.size} document(s) updated.`);
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Bulk update failed.'),
  });

  const bulkDeleteMutation = useMutation({
    mutationFn: () => api.post('/documents/bulk-delete', { doc_ids: Array.from(selectedIds) }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['trash'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      setSelectedIds(new Set());
      setIsSelecting(false);
      Alert.alert('Deleted', res.data?.message || `${selectedIds.size} document(s) moved to trash.`);
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Bulk delete failed.'),
  });

  const assignBatchMutation = useMutation({
    mutationFn: (staff_username: string) =>
      api.post('/admin/assign-doc-batch', { doc_ids: Array.from(selectedIds), staff_username }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      setSelectedIds(new Set());
      setIsSelecting(false);
      setAssignModal(false);
      setSelectedStaff(null);
      setStaffSearch('');
      Alert.alert('Assigned', `${res.data?.assigned ?? 0} document(s) assigned to ${res.data?.staff}.`);
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Assign failed.'),
  });

  const deleteUnassignedMutation = useMutation({
    mutationFn: () =>
      api.post('/admin/delete-unassigned-batch', { doc_ids: Array.from(selectedIds), delete_all: false }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      setSelectedIds(new Set());
      setIsSelecting(false);
      Alert.alert('Done', `${res.data?.deleted ?? 0} unassigned document(s) deleted.`);
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Delete failed.'),
  });

  const deleteAllUnassignedMutation = useMutation({
    mutationFn: () =>
      api.post('/admin/delete-unassigned-batch', { doc_ids: [], delete_all: true }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      setDeleteAllModal(false);
      setDeleteAllConfirmText('');
      Alert.alert('Done', `${res.data?.deleted ?? 0} unassigned document(s) deleted.`);
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Operation failed.'),
  });

  // ── Handlers ───────────────────────────────────────────────────────────────

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => setSelectedIds(new Set(docs.map((d: any) => d.id)));
  const clearSelection = () => setSelectedIds(new Set());

  const exitSelectMode = () => {
    setIsSelecting(false);
    setSelectedIds(new Set());
  };

  const handleBulkDelete = () => {
    if (selectedIds.size === 0) return;
    Alert.alert(
      'Bulk Delete',
      `Move ${selectedIds.size} document${selectedIds.size !== 1 ? 's' : ''} to trash?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Move to Trash', style: 'destructive', onPress: () => bulkDeleteMutation.mutate() },
      ],
    );
  };

  const handleDeleteUnassigned = () => {
    if (selectedIds.size === 0) return;
    Alert.alert(
      'Delete Unassigned',
      `Only documents with no assigned staff will be deleted. Documents already assigned to someone will be skipped.\n\nProceed with ${selectedIds.size} selected?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete Unassigned', style: 'destructive', onPress: () => deleteUnassignedMutation.mutate() },
      ],
    );
  };

  const handleConfirmAssign = () => {
    if (!selectedStaff) { Alert.alert('No Staff Selected', 'Please select a staff member.'); return; }
    assignBatchMutation.mutate(selectedStaff);
  };

  const handleDeleteAllUnassigned = () => {
    if (deleteAllConfirmText.trim().toUpperCase() !== 'DELETE') {
      Alert.alert('Confirmation Required', 'Type DELETE in the box to confirm.');
      return;
    }
    deleteAllUnassignedMutation.mutate();
  };

  // ── Filtered staff for picker ──────────────────────────────────────────────

  const filteredStaff = staffList.filter((s) => {
    const q = staffSearch.toLowerCase();
    return (
      s.full_name?.toLowerCase().includes(q) ||
      s.username?.toLowerCase().includes(q) ||
      s.office?.toLowerCase().includes(q)
    );
  });

  // ── Render item ────────────────────────────────────────────────────────────

  const renderDoc = ({ item }: { item: any }) => {
    const s = getStatus(item.status);
    const isSelected = selectedIds.has(item.id);

    return (
      <TouchableOpacity
        onPress={() => {
          if (isSelecting) toggleSelect(item.id);
          else router.push(`/(app)/documents/${item.id}`);
        }}
        onLongPress={() => {
          if (!isSelecting && (isAdmin || user?.role === 'staff')) {
            setIsSelecting(true);
            setSelectedIds(new Set([item.id]));
          }
        }}
        activeOpacity={0.75}
        style={{
          backgroundColor: isSelected ? '#EFF6FF' : '#fff',
          borderRadius: 14,
          padding: 16,
          marginBottom: 10,
          borderWidth: isSelected ? 1.5 : 0.5,
          borderColor: isSelected ? '#0038A8' : '#E2E8F0',
          flexDirection: 'row',
          alignItems: 'center',
          gap: 12,
        }}
      >
        {/* Checkbox (select mode) or accent bar */}
        {isSelecting ? (
          <View style={{ width: 24, alignItems: 'center' }}>
            {isSelected
              ? <CheckSquare size={22} color="#0038A8" />
              : <Square size={22} color="#CBD5E1" />}
          </View>
        ) : (
          <View style={{
            width: 3, height: 44, borderRadius: 2,
            backgroundColor: s.accent, opacity: 0.6,
          }} />
        )}

        <View style={{ flex: 1 }}>
          {/* Top row: doc ID + status badge */}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
            <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 13.5, letterSpacing: -0.2 }}>
              {item.doc_id || item.id?.slice(0, 8).toUpperCase()}
            </Text>
            <View style={{ backgroundColor: s.bg, borderRadius: 20, paddingHorizontal: 9, paddingVertical: 3 }}>
              <Text style={{ color: s.text, fontSize: 11, fontWeight: '700' }}>
                {item.status}
              </Text>
            </View>
          </View>

          {/* Doc name */}
          <Text style={{ color: '#334155', fontSize: 13, marginBottom: 5, lineHeight: 18 }} numberOfLines={2}>
            {item.doc_name || 'No name'}
          </Text>

          {/* Footer row: office + date */}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Text style={{ color: '#94A3B8', fontSize: 11.5 }} numberOfLines={1}>
              {item.from_office || item.sender_org || '—'}
            </Text>
            <Text style={{ color: '#94A3B8', fontSize: 11.5 }}>
              {item.doc_date || item.created_at?.slice(0, 10) || '—'}
            </Text>
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  // ── Screen ──────────────────────────────────────────────────────────────────

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC', paddingBottom: 100 }}>
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />
      <OfflineBanner />

      {/* ── Hero header ── */}
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20, overflow: 'hidden' }}>
        {/* Grid texture */}
        {[...Array(3)].map((_, i) => (
          <View key={`h${i}`} style={{
            position: 'absolute', top: (i + 1) * 28, left: 0, right: 0,
            height: 1, backgroundColor: '#fff', opacity: 0.05,
          }} />
        ))}
        {[...Array(4)].map((_, i) => (
          <View key={`v${i}`} style={{
            position: 'absolute', left: (i + 1) * (width / 5), top: 0, bottom: 0,
            width: 1, backgroundColor: '#fff', opacity: 0.05,
          }} />
        ))}
        {/* Yellow accent circle */}
        <View style={{
          position: 'absolute', top: -40, right: -40,
          width: 130, height: 130, borderRadius: 65,
          backgroundColor: '#FCD116', opacity: 0.10,
        }} />

        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <Text style={{ color: '#fff', fontSize: 22, fontWeight: '800', letterSpacing: -0.4 }}>
            Documents
          </Text>

          {/* Admin-only header actions */}
          {isAdmin && (
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {/* Delete All Unassigned */}
              {!isSelecting && (
                <TouchableOpacity
                  onPress={() => { setDeleteAllConfirmText(''); setDeleteAllModal(true); }}
                  style={{
                    backgroundColor: 'rgba(239,68,68,0.20)',
                    borderRadius: 10, paddingHorizontal: 10, paddingVertical: 7,
                    borderWidth: 1, borderColor: 'rgba(239,68,68,0.35)',
                  }}
                >
                  <Text style={{ color: '#FCA5A5', fontSize: 11, fontWeight: '700' }}>Del Unassigned</Text>
                </TouchableOpacity>
              )}

              {/* Select / Cancel toggle */}
              <TouchableOpacity
                onPress={() => isSelecting ? exitSelectMode() : setIsSelecting(true)}
                style={{
                  backgroundColor: isSelecting ? '#EF4444' : 'rgba(255,255,255,0.18)',
                  borderRadius: 10, paddingHorizontal: 12, paddingVertical: 7,
                  borderWidth: 1, borderColor: isSelecting ? '#EF4444' : 'rgba(255,255,255,0.25)',
                }}
              >
                <Text style={{ color: '#fff', fontSize: 12, fontWeight: '700' }}>
                  {isSelecting ? 'Cancel' : 'Select'}
                </Text>
              </TouchableOpacity>
            </View>
          )}
        </View>

        {/* Search bar + Filter button */}
        <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
          <View style={{
            flex: 1, flexDirection: 'row', gap: 8,
            backgroundColor: 'rgba(255,255,255,0.15)',
            borderRadius: 13, paddingHorizontal: 14, paddingVertical: 2,
            borderWidth: 1, borderColor: 'rgba(255,255,255,0.20)',
            alignItems: 'center',
          }}>
            <Search size={16} color="rgba(255,255,255,0.60)" />
            <TextInput
              value={searchInput}
              onChangeText={setSearchInput}
              onSubmitEditing={handleSearch}
              returnKeyType="search"
              placeholder="Search documents..."
              placeholderTextColor="rgba(255,255,255,0.45)"
              style={{ flex: 1, paddingVertical: 11, color: '#fff', fontSize: 14 }}
            />
            <TouchableOpacity
              onPress={handleSearch}
              style={{
                backgroundColor: '#fff',
                borderRadius: 9,
                paddingHorizontal: 14,
                paddingVertical: 7,
              }}
            >
              <Text style={{ color: '#0038A8', fontWeight: '700', fontSize: 13 }}>Search</Text>
            </TouchableOpacity>
          </View>

          {/* Filter toggle */}
          <TouchableOpacity
            onPress={() => setShowFilterPanel((v) => !v)}
            style={{
              backgroundColor: showFilterPanel ? '#FCD116' : 'rgba(255,255,255,0.18)',
              borderRadius: 13, padding: 11,
              borderWidth: 1, borderColor: showFilterPanel ? '#FCD116' : 'rgba(255,255,255,0.25)',
              alignItems: 'center', justifyContent: 'center',
            }}
          >
            <Filter size={18} color={showFilterPanel ? '#0038A8' : '#fff'} />
            {activeFilterCount > 0 && (
              <View style={{
                position: 'absolute', top: -5, right: -5,
                width: 18, height: 18, borderRadius: 9,
                backgroundColor: '#EF4444',
                alignItems: 'center', justifyContent: 'center',
              }}>
                <Text style={{ color: '#fff', fontSize: 10, fontWeight: '800' }}>{activeFilterCount}</Text>
              </View>
            )}
          </TouchableOpacity>

          {/* Export CSV */}
          {(isAdmin || user?.role === 'staff') && (
            <TouchableOpacity
              onPress={handleExport}
              disabled={isExporting}
              style={{
                backgroundColor: 'rgba(255,255,255,0.18)',
                borderRadius: 13, padding: 11,
                borderWidth: 1, borderColor: 'rgba(255,255,255,0.25)',
                alignItems: 'center', justifyContent: 'center',
                opacity: isExporting ? 0.7 : 1,
              }}
            >
              {isExporting
                ? <ActivityIndicator size="small" color="#fff" />
                : <Download size={18} color="#fff" />}
            </TouchableOpacity>
          )}
        </View>

        {/* Cached data notice */}
        {isFromCache && (
          <View style={{
            marginTop: 12,
            backgroundColor: 'rgba(255,255,255,0.10)',
            borderRadius: 10, padding: 10,
            flexDirection: 'row', alignItems: 'center', gap: 8,
            borderWidth: 1, borderColor: 'rgba(255,255,255,0.15)',
          }}>
            <Text style={{ fontSize: 13 }}>💾</Text>
            <Text style={{ color: '#FCD34D', fontSize: 12, flex: 1 }}>
              Showing cached data — pull to refresh when online
            </Text>
          </View>
        )}
      </View>

      {/* ── Filter pills ── */}
      <View style={{ backgroundColor: '#fff', borderBottomWidth: 0.5, borderBottomColor: '#E2E8F0' }}>
        <FlatList
          horizontal
          data={STATUS_FILTERS}
          keyExtractor={(i) => i}
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ paddingHorizontal: 16, paddingVertical: 10, gap: 8 }}
          renderItem={({ item }) => (
            <TouchableOpacity
              onPress={() => setActiveFilter(item)}
              style={{
                paddingHorizontal: 16,
                paddingVertical: 6,
                borderRadius: 20,
                backgroundColor: activeFilter === item ? '#0038A8' : '#F1F5F9',
                borderWidth: activeFilter === item ? 0 : 0.5,
                borderColor: '#E2E8F0',
              }}
            >
              <Text style={{
                color: activeFilter === item ? '#fff' : '#64748B',
                fontWeight: '700',
                fontSize: 12.5,
              }}>
                {item}
              </Text>
            </TouchableOpacity>
          )}
        />
      </View>

      {/* ── Advanced Filter Panel ── */}
      {showFilterPanel && (
        <View style={{
          backgroundColor: '#fff', marginHorizontal: 16, marginTop: 10,
          borderRadius: 16, padding: 16,
          borderWidth: 0.5, borderColor: '#E2E8F0',
          shadowColor: '#000', shadowOffset: { width: 0, height: 2 },
          shadowOpacity: 0.06, shadowRadius: 8, elevation: 3,
        }}>
          {/* Office */}
          <View style={{ marginBottom: 12 }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>Office</Text>
            <TouchableOpacity
              onPress={() => { setPickerSearch(''); setPickerModal('office'); }}
              style={{
                flexDirection: 'row', alignItems: 'center',
                backgroundColor: '#F8FAFC', borderRadius: 10,
                paddingHorizontal: 14, paddingVertical: 11,
                borderWidth: 0.5, borderColor: filterOffice ? '#0038A8' : '#E2E8F0',
              }}
            >
              <Text style={{ color: filterOffice ? '#1E293B' : '#94A3B8', fontSize: 13, flex: 1 }}>
                {filterOffice || 'Any office'}
              </Text>
              {filterOffice ? (
                <TouchableOpacity onPress={() => setFilterOffice('')} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                  <X size={14} color="#94A3B8" />
                </TouchableOpacity>
              ) : (
                <Text style={{ color: '#94A3B8', fontSize: 13 }}>›</Text>
              )}
            </TouchableOpacity>
          </View>

          {/* Category */}
          <View style={{ marginBottom: 12 }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>Category</Text>
            <TouchableOpacity
              onPress={() => { setPickerSearch(''); setPickerModal('category'); }}
              style={{
                flexDirection: 'row', alignItems: 'center',
                backgroundColor: '#F8FAFC', borderRadius: 10,
                paddingHorizontal: 14, paddingVertical: 11,
                borderWidth: 0.5, borderColor: filterCat ? '#0038A8' : '#E2E8F0',
              }}
            >
              <Text style={{ color: filterCat ? '#1E293B' : '#94A3B8', fontSize: 13, flex: 1 }}>
                {filterCat || 'Any category'}
              </Text>
              {filterCat ? (
                <TouchableOpacity onPress={() => setFilterCat('')} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                  <X size={14} color="#94A3B8" />
                </TouchableOpacity>
              ) : (
                <Text style={{ color: '#94A3B8', fontSize: 13 }}>›</Text>
              )}
            </TouchableOpacity>
          </View>

          {/* Staff Member */}
          <View style={{ marginBottom: 12 }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>Staff Member</Text>
            <TouchableOpacity
              onPress={() => { setPickerSearch(''); setPickerModal('staff'); }}
              style={{
                flexDirection: 'row', alignItems: 'center',
                backgroundColor: '#F8FAFC', borderRadius: 10,
                paddingHorizontal: 14, paddingVertical: 11,
                borderWidth: 0.5, borderColor: filterStaff ? '#0038A8' : '#E2E8F0',
              }}
            >
              <Text style={{ color: filterStaff ? '#1E293B' : '#94A3B8', fontSize: 13, flex: 1 }}>
                {filterStaffLabel || 'Any staff member'}
              </Text>
              {filterStaff ? (
                <TouchableOpacity onPress={() => setFilterStaff('')} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                  <X size={14} color="#94A3B8" />
                </TouchableOpacity>
              ) : (
                <Text style={{ color: '#94A3B8', fontSize: 13 }}>›</Text>
              )}
            </TouchableOpacity>
          </View>

          {/* Source */}
          <View style={{ marginBottom: 12 }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>Source</Text>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {['Staff', 'Client'].map((src) => (
                <TouchableOpacity
                  key={src}
                  onPress={() => setFilterSource(filterSource === src ? '' : src)}
                  style={{
                    flex: 1, paddingVertical: 10, borderRadius: 10, alignItems: 'center',
                    backgroundColor: filterSource === src ? '#0038A8' : '#F1F5F9',
                    borderWidth: filterSource === src ? 0 : 0.5,
                    borderColor: '#E2E8F0',
                  }}
                >
                  <Text style={{ color: filterSource === src ? '#fff' : '#64748B', fontWeight: '700', fontSize: 13 }}>{src}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {/* Date From */}
          <View style={{ marginBottom: 12 }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>From Date</Text>
            <TextInput
              value={filterDateFrom}
              onChangeText={setFilterDateFrom}
              placeholder="YYYY-MM-DD"
              placeholderTextColor="#CBD5E1"
              keyboardType="numeric"
              style={{
                backgroundColor: '#F8FAFC', borderRadius: 10,
                paddingHorizontal: 14, paddingVertical: 11,
                borderWidth: 0.5, borderColor: filterDateFrom ? '#0038A8' : '#E2E8F0',
                fontSize: 13, color: '#1E293B',
              }}
            />
          </View>

          {/* Date To */}
          <View style={{ marginBottom: activeFilterCount > 0 ? 12 : 0 }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>To Date</Text>
            <TextInput
              value={filterDateTo}
              onChangeText={setFilterDateTo}
              placeholder="YYYY-MM-DD"
              placeholderTextColor="#CBD5E1"
              keyboardType="numeric"
              style={{
                backgroundColor: '#F8FAFC', borderRadius: 10,
                paddingHorizontal: 14, paddingVertical: 11,
                borderWidth: 0.5, borderColor: filterDateTo ? '#0038A8' : '#E2E8F0',
                fontSize: 13, color: '#1E293B',
              }}
            />
          </View>

          {/* Clear All */}
          {activeFilterCount > 0 && (
            <TouchableOpacity
              onPress={clearAllFilters}
              style={{ backgroundColor: '#FEE2E2', borderRadius: 10, paddingVertical: 10, alignItems: 'center' }}
            >
              <Text style={{ color: '#DC2626', fontWeight: '700', fontSize: 13 }}>Clear All Filters</Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      {/* ── Result count / Selection bar ── */}
      <View style={{ paddingHorizontal: 20, paddingTop: 14, paddingBottom: 6, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        {isSelecting ? (
          <>
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#0038A8', textTransform: 'uppercase', letterSpacing: 0.8 }}>
              {selectedIds.size} selected
            </Text>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TouchableOpacity
                onPress={selectedIds.size === docs.length ? clearSelection : selectAll}
                style={{ backgroundColor: '#EFF6FF', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5 }}
              >
                <Text style={{ color: '#0038A8', fontSize: 12, fontWeight: '700' }}>
                  {selectedIds.size === docs.length ? 'Deselect All' : 'Select All'}
                </Text>
              </TouchableOpacity>
            </View>
          </>
        ) : (
          <>
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#0038A8', textTransform: 'uppercase', letterSpacing: 0.8 }}>
              {isLoading ? 'Loading...' : `${data?.total ?? 0} documents found`}
            </Text>
            {!isOnline && (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: '#F87171' }} />
                <Text style={{ color: '#F87171', fontSize: 12, fontWeight: '600' }}>Offline</Text>
              </View>
            )}
          </>
        )}
      </View>

      {/* ── List ── */}
      {isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator size="large" color="#0038A8" />
          <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 12 }}>Loading documents...</Text>
        </View>
      ) : (
        <FlatList
          data={docs}
          keyExtractor={(item) => item.id}
          renderItem={renderDoc}
          contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 4, paddingBottom: isSelecting ? 120 : 16 }}
          refreshControl={
            <RefreshControl
              refreshing={isRefetching}
              onRefresh={refetch}
              tintColor="#0038A8"
            />
          }
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingTop: 72 }}>
              <View style={{
                width: 72, height: 72, borderRadius: 36,
                backgroundColor: '#EFF6FF',
                alignItems: 'center', justifyContent: 'center',
                marginBottom: 16,
              }}>
                <Text style={{ fontSize: 32 }}>📄</Text>
              </View>
              <Text style={{ color: '#1E293B', fontSize: 16, fontWeight: '700', marginBottom: 6 }}>
                No documents found
              </Text>
              <Text style={{ color: '#94A3B8', fontSize: 13, textAlign: 'center', paddingHorizontal: 40 }}>
                Try adjusting your search or filter to find what you're looking for.
              </Text>
            </View>
          }
        />
      )}

      {/* ── Batch Action Toolbar ── */}
      {isSelecting && (
        <View style={{
          position: 'absolute', bottom: 100, left: 16, right: 16,
          backgroundColor: '#1E293B', borderRadius: 16, padding: 14,
          shadowColor: '#000', shadowOffset: { width: 0, height: 4 },
          shadowOpacity: 0.25, shadowRadius: 12, elevation: 8,
        }}>
          {/* Header — always visible once select mode is active */}
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: selectedIds.size > 0 ? 10 : 0 }}>
            <TouchableOpacity onPress={exitSelectMode} style={{ padding: 4 }}>
              <X size={20} color="#94A3B8" />
            </TouchableOpacity>
            <Text style={{ color: '#fff', fontSize: 13, fontWeight: '700', flex: 1, marginLeft: 10 }}>
              {selectedIds.size > 0 ? `${selectedIds.size} selected` : 'Tap items to select'}
            </Text>
          </View>

          {/* Action buttons — only appear once ≥1 item is selected */}
          {selectedIds.size > 0 && (
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              {/* Status — all staff */}
              <TouchableOpacity
                onPress={() => setBulkStatusModal(true)}
                disabled={bulkStatusMutation.isPending}
                style={{
                  backgroundColor: '#3B82F6', borderRadius: 10,
                  paddingHorizontal: 12, paddingVertical: 8,
                  flexDirection: 'row', alignItems: 'center', gap: 5, flex: 1,
                }}
              >
                <RefreshCw size={14} color="#fff" />
                <Text style={{ color: '#fff', fontSize: 12, fontWeight: '700' }}>Status</Text>
              </TouchableOpacity>

              {/* Assign to Staff — admin only */}
              {isAdmin && (
                <TouchableOpacity
                  onPress={() => { setSelectedStaff(null); setStaffSearch(''); setAssignModal(true); }}
                  disabled={assignBatchMutation.isPending}
                  style={{
                    backgroundColor: '#10B981', borderRadius: 10,
                    paddingHorizontal: 12, paddingVertical: 8,
                    flexDirection: 'row', alignItems: 'center', gap: 5, flex: 1,
                  }}
                >
                  <UserCheck size={14} color="#fff" />
                  <Text style={{ color: '#fff', fontSize: 12, fontWeight: '700' }}>Assign</Text>
                </TouchableOpacity>
              )}

              {/* Delete Unassigned — admin only */}
              {isAdmin && (
                <TouchableOpacity
                  onPress={handleDeleteUnassigned}
                  disabled={deleteUnassignedMutation.isPending}
                  style={{
                    backgroundColor: '#F59E0B', borderRadius: 10,
                    paddingHorizontal: 12, paddingVertical: 8,
                    flexDirection: 'row', alignItems: 'center', gap: 5, flex: 1,
                  }}
                >
                  {deleteUnassignedMutation.isPending
                    ? <ActivityIndicator size="small" color="#fff" />
                    : <Trash2 size={14} color="#fff" />}
                  <Text style={{ color: '#fff', fontSize: 12, fontWeight: '700' }}>Del Unassigned</Text>
                </TouchableOpacity>
              )}

              {/* Delete (to trash) — admin only */}
              {isAdmin && (
                <TouchableOpacity
                  onPress={handleBulkDelete}
                  disabled={bulkDeleteMutation.isPending}
                  style={{
                    backgroundColor: '#EF4444', borderRadius: 10,
                    paddingHorizontal: 12, paddingVertical: 8,
                    flexDirection: 'row', alignItems: 'center', gap: 5, flex: 1,
                  }}
                >
                  {bulkDeleteMutation.isPending
                    ? <ActivityIndicator size="small" color="#fff" />
                    : <Trash2 size={14} color="#fff" />}
                  <Text style={{ color: '#fff', fontSize: 12, fontWeight: '700' }}>Trash</Text>
                </TouchableOpacity>
              )}
            </View>
          )}
        </View>
      )}

      {/* ── Bulk Status Modal ── */}
      <Modal visible={bulkStatusModal} animationType="slide" transparent>
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' }}>
          <TouchableOpacity
            style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
            onPress={() => { setBulkStatusModal(false); setSelectedBulkStatus(null); setBulkRemarks(''); }}
            activeOpacity={1}
          />
          <View style={{
            backgroundColor: '#F8FAFC', borderTopLeftRadius: 24, borderTopRightRadius: 24,
            padding: 20, paddingBottom: 40,
          }}>
            {/* Header */}
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 17 }}>
                Update Status · {selectedIds.size} doc{selectedIds.size !== 1 ? 's' : ''}
              </Text>
              <TouchableOpacity onPress={() => { setBulkStatusModal(false); setSelectedBulkStatus(null); setBulkRemarks(''); }}>
                <X size={20} color="#94A3B8" />
              </TouchableOpacity>
            </View>

            {/* Remarks — shown first so user fills it before picking a status */}
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8 }}>
              Remarks (optional)
            </Text>
            <TextInput
              value={bulkRemarks}
              onChangeText={setBulkRemarks}
              placeholder="Add a note about this status change…"
              placeholderTextColor="#94A3B8"
              multiline
              style={{
                backgroundColor: '#fff', borderRadius: 12, padding: 12,
                borderWidth: 1, borderColor: '#E2E8F0', fontSize: 14, color: '#1E293B',
                height: 72, textAlignVertical: 'top', marginBottom: 16,
              }}
            />

            {/* Status pills — tap to select, highlighted when chosen */}
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 10 }}>
              Select New Status
            </Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 20 }}>
              {ALL_STATUSES.map((s) => {
                const cfg = getStatus(s);
                const isChosen = selectedBulkStatus === s;
                return (
                  <TouchableOpacity
                    key={s}
                    onPress={() => setSelectedBulkStatus(isChosen ? null : s)}
                    style={{
                      backgroundColor: isChosen ? cfg.accent : cfg.bg,
                      borderRadius: 20, paddingHorizontal: 14, paddingVertical: 8,
                      borderWidth: isChosen ? 2 : 0,
                      borderColor: isChosen ? cfg.accent : 'transparent',
                    }}
                  >
                    <Text style={{ color: isChosen ? '#fff' : cfg.text, fontWeight: '700', fontSize: 13 }}>{s}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Action buttons */}
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity
                onPress={() => { setBulkStatusModal(false); setSelectedBulkStatus(null); setBulkRemarks(''); }}
                style={{
                  flex: 1, backgroundColor: '#F1F5F9', borderRadius: 13,
                  paddingVertical: 14, alignItems: 'center',
                }}
              >
                <Text style={{ color: '#475569', fontWeight: '700', fontSize: 14 }}>Cancel</Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => {
                  if (!selectedBulkStatus) return;
                  bulkStatusMutation.mutate({ status: selectedBulkStatus, remarks: bulkRemarks });
                }}
                disabled={!selectedBulkStatus || bulkStatusMutation.isPending}
                style={{
                  flex: 2, borderRadius: 13, paddingVertical: 14,
                  alignItems: 'center', justifyContent: 'center',
                  flexDirection: 'row', gap: 8,
                  backgroundColor: selectedBulkStatus ? '#0038A8' : '#E2E8F0',
                }}
              >
                {bulkStatusMutation.isPending
                  ? <ActivityIndicator size="small" color="#fff" />
                  : <RefreshCw size={15} color={selectedBulkStatus ? '#fff' : '#94A3B8'} />}
                <Text style={{ color: selectedBulkStatus ? '#fff' : '#94A3B8', fontWeight: '700', fontSize: 14 }}>
                  {bulkStatusMutation.isPending
                    ? 'Applying…'
                    : selectedBulkStatus
                      ? `Apply to ${selectedIds.size} document${selectedIds.size !== 1 ? 's' : ''}`
                      : 'Select a status'}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* ── Assign to Staff Modal ── */}
      <Modal visible={assignModal} animationType="slide" transparent>
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' }}>
          <TouchableOpacity
            style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
            onPress={() => setAssignModal(false)}
            activeOpacity={1}
          />
          <View style={{
            backgroundColor: '#F8FAFC', borderTopLeftRadius: 24, borderTopRightRadius: 24,
            padding: 20, paddingBottom: 40, maxHeight: '75%',
          }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Users size={18} color="#0038A8" />
                <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 17 }}>
                  Assign to Staff · {selectedIds.size} doc{selectedIds.size !== 1 ? 's' : ''}
                </Text>
              </View>
              <TouchableOpacity onPress={() => setAssignModal(false)}>
                <X size={20} color="#94A3B8" />
              </TouchableOpacity>
            </View>

            {/* Staff search */}
            <View style={{
              flexDirection: 'row', alignItems: 'center', gap: 8,
              backgroundColor: '#fff', borderRadius: 12,
              borderWidth: 1, borderColor: '#E2E8F0',
              paddingHorizontal: 12, marginBottom: 12,
            }}>
              <Search size={15} color="#94A3B8" />
              <TextInput
                value={staffSearch}
                onChangeText={setStaffSearch}
                placeholder="Search staff by name or office…"
                placeholderTextColor="#CBD5E1"
                style={{ flex: 1, paddingVertical: 11, fontSize: 14, color: '#1E293B' }}
              />
            </View>

            {/* Staff list */}
            <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
              {filteredStaff.length === 0 ? (
                <Text style={{ color: '#94A3B8', textAlign: 'center', marginTop: 24, fontSize: 13 }}>
                  No staff found
                </Text>
              ) : (
                filteredStaff.map((s) => {
                  const isChosen = selectedStaff === s.username;
                  return (
                    <TouchableOpacity
                      key={s.username}
                      onPress={() => setSelectedStaff(isChosen ? null : s.username)}
                      style={{
                        flexDirection: 'row', alignItems: 'center', gap: 12,
                        backgroundColor: isChosen ? '#EFF6FF' : '#fff',
                        borderRadius: 12, padding: 14, marginBottom: 8,
                        borderWidth: isChosen ? 1.5 : 0.5,
                        borderColor: isChosen ? '#0038A8' : '#E2E8F0',
                      }}
                    >
                      <View style={{
                        width: 38, height: 38, borderRadius: 19,
                        backgroundColor: isChosen ? '#0038A8' : '#F1F5F9',
                        alignItems: 'center', justifyContent: 'center',
                      }}>
                        <Text style={{ fontSize: 15, fontWeight: '800', color: isChosen ? '#fff' : '#64748B' }}>
                          {(s.full_name || s.username).charAt(0).toUpperCase()}
                        </Text>
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontWeight: '700', color: '#1E293B', fontSize: 14 }}>
                          {s.full_name || s.username}
                        </Text>
                        <Text style={{ color: '#94A3B8', fontSize: 12 }}>
                          {s.office || s.role || '—'}
                        </Text>
                      </View>
                      {isChosen && <CheckSquare size={20} color="#0038A8" />}
                    </TouchableOpacity>
                  );
                })
              )}
            </ScrollView>

            {/* Confirm button */}
            <TouchableOpacity
              onPress={handleConfirmAssign}
              disabled={!selectedStaff || assignBatchMutation.isPending}
              style={{
                marginTop: 16,
                backgroundColor: selectedStaff ? '#0038A8' : '#E2E8F0',
                borderRadius: 13, paddingVertical: 15,
                flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
              }}
            >
              {assignBatchMutation.isPending
                ? <ActivityIndicator size="small" color="#fff" />
                : <UserCheck size={16} color={selectedStaff ? '#fff' : '#94A3B8'} />}
              <Text style={{ color: selectedStaff ? '#fff' : '#94A3B8', fontSize: 15, fontWeight: '700' }}>
                {assignBatchMutation.isPending ? 'Assigning…' : 'Confirm Assign'}
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* ── Generic Picker Modal (Office / Category / Staff) ── */}
      <Modal visible={pickerModal !== null} animationType="slide" transparent>
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' }}>
          <TouchableOpacity
            style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
            onPress={() => { setPickerModal(null); setPickerSearch(''); }}
            activeOpacity={1}
          />
          <View style={{
            backgroundColor: '#F8FAFC', borderTopLeftRadius: 24, borderTopRightRadius: 24,
            padding: 20, paddingBottom: 40, maxHeight: '70%',
          }}>
            {/* Header */}
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 17 }}>
                Select {pickerLabel}
              </Text>
              <TouchableOpacity onPress={() => { setPickerModal(null); setPickerSearch(''); }}>
                <X size={20} color="#94A3B8" />
              </TouchableOpacity>
            </View>

            {/* Search */}
            <View style={{
              flexDirection: 'row', alignItems: 'center', gap: 8,
              backgroundColor: '#fff', borderRadius: 12,
              borderWidth: 1, borderColor: '#E2E8F0',
              paddingHorizontal: 12, marginBottom: 10,
            }}>
              <Search size={15} color="#94A3B8" />
              <TextInput
                value={pickerSearch}
                onChangeText={setPickerSearch}
                placeholder={`Search ${pickerLabel.toLowerCase()}…`}
                placeholderTextColor="#CBD5E1"
                style={{ flex: 1, paddingVertical: 11, fontSize: 14, color: '#1E293B' }}
              />
            </View>

            {/* Clear selection row */}
            {currentPickerValue !== '' && (
              <TouchableOpacity
                onPress={clearPickerValue}
                style={{
                  paddingVertical: 12, paddingHorizontal: 4, marginBottom: 4,
                  flexDirection: 'row', alignItems: 'center', gap: 8,
                }}
              >
                <X size={14} color="#EF4444" />
                <Text style={{ color: '#EF4444', fontWeight: '700', fontSize: 13 }}>Clear selection</Text>
              </TouchableOpacity>
            )}

            {/* Options list */}
            <ScrollView showsVerticalScrollIndicator={false}>
              {filteredPickerOptions.length === 0 ? (
                <Text style={{ color: '#94A3B8', textAlign: 'center', marginTop: 24, fontSize: 13 }}>
                  No options found
                </Text>
              ) : (
                filteredPickerOptions.map((opt) => {
                  const isActive = opt === currentPickerValue;
                  return (
                    <TouchableOpacity
                      key={opt}
                      onPress={() => applyPickerValue(opt)}
                      style={{
                        paddingVertical: 13, paddingHorizontal: 14,
                        borderRadius: 12, marginBottom: 4,
                        backgroundColor: isActive ? '#EFF6FF' : '#fff',
                        borderWidth: isActive ? 1.5 : 0.5,
                        borderColor: isActive ? '#0038A8' : '#E2E8F0',
                        flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                      }}
                    >
                      <Text style={{ color: isActive ? '#0038A8' : '#1E293B', fontWeight: isActive ? '700' : '400', fontSize: 14 }}>
                        {opt}
                      </Text>
                      {isActive && <CheckSquare size={18} color="#0038A8" />}
                    </TouchableOpacity>
                  );
                })
              )}
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* ── Delete All Unassigned Modal ── */}
      <Modal visible={deleteAllModal} animationType="fade" transparent>
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'center', paddingHorizontal: 24 }}>
          <View style={{ backgroundColor: '#fff', borderRadius: 20, padding: 24 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <Trash2 size={20} color="#EF4444" />
              <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 17 }}>Delete All Unassigned</Text>
            </View>

            <Text style={{ color: '#475569', fontSize: 13, lineHeight: 20, marginBottom: 16 }}>
              This will permanently soft-delete ALL documents with no assigned staff. Documents already assigned to someone are unaffected. This cannot be easily undone.
            </Text>

            <Text style={{ fontSize: 11, fontWeight: '700', color: '#EF4444', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8 }}>
              Type DELETE to confirm
            </Text>
            <TextInput
              value={deleteAllConfirmText}
              onChangeText={setDeleteAllConfirmText}
              placeholder="DELETE"
              autoCapitalize="characters"
              placeholderTextColor="#CBD5E1"
              style={{
                backgroundColor: '#F8FAFC', borderRadius: 12,
                paddingHorizontal: 14, paddingVertical: 12, marginBottom: 20,
                borderWidth: 1.5,
                borderColor: deleteAllConfirmText.trim().toUpperCase() === 'DELETE' ? '#EF4444' : '#E2E8F0',
                fontSize: 15, color: '#1E293B', fontWeight: '700',
              }}
            />

            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity
                onPress={() => { setDeleteAllModal(false); setDeleteAllConfirmText(''); }}
                style={{
                  flex: 1, backgroundColor: '#F1F5F9', borderRadius: 12,
                  paddingVertical: 13, alignItems: 'center',
                }}
              >
                <Text style={{ color: '#475569', fontWeight: '700', fontSize: 14 }}>Cancel</Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={handleDeleteAllUnassigned}
                disabled={deleteAllUnassignedMutation.isPending}
                style={{
                  flex: 1, backgroundColor: '#EF4444', borderRadius: 12,
                  paddingVertical: 13, alignItems: 'center',
                  flexDirection: 'row', justifyContent: 'center', gap: 6,
                  opacity: deleteAllUnassignedMutation.isPending ? 0.7 : 1,
                }}
              >
                {deleteAllUnassignedMutation.isPending
                  ? <ActivityIndicator size="small" color="#fff" />
                  : <Trash2 size={15} color="#fff" />}
                <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>Delete All</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}
