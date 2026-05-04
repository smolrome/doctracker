import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';
import { documentService } from '../services/documents';
import { authService } from '../services/auth';
import { Stats, Document } from '../types';

interface DashboardScreenProps {
  onLogout: () => void;
}

export default function DashboardScreen({ onLogout }: DashboardScreenProps) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    try {
      const [statsData, docsData] = await Promise.all([
        documentService.getStats(),
        documentService.getDocuments({ limit: 10 }),
      ]);
      setStats(statsData);
      setDocuments(docsData.documents);
    } catch (error) {
      Alert.alert('Error', 'Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  useFocusEffect(
    useCallback(() => {
      loadData();
    }, [])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  };

  const handleLogout = async () => {
    await authService.logout();
    onLogout();
  };

  const renderStatCard = (title: string, value: number, color: string) => (
    <View style={[styles.statCard, { borderLeftColor: color }]}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statTitle}>{title}</Text>
    </View>
  );

  const renderDocument = ({ item }: { item: Document }) => (
    <View style={styles.docItem}>
      <View style={styles.docHeader}>
        <Text style={styles.docRef}>{item.ref || item.id}</Text>
        <Text style={[styles.docStatus, getStatusStyle(item.status)]}>
          {item.status}
        </Text>
      </View>
      <Text style={styles.docSubject} numberOfLines={2}>
        {item.subject}
      </Text>
      <Text style={styles.docOffice}>{item.office}</Text>
    </View>
  );

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <Text>Loading...</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Dashboard</Text>
        <TouchableOpacity onPress={handleLogout} style={styles.logoutBtn}>
          <Text style={styles.logoutText}>Logout</Text>
        </TouchableOpacity>
      </View>

      <FlatList
        data={documents}
        renderItem={renderDocument}
        keyExtractor={(item) => item.id}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
        ListHeaderComponent={
          stats ? (
            <View style={styles.statsContainer}>
              <Text style={styles.sectionTitle}>Overview</Text>
              <View style={styles.statsGrid}>
                {renderStatCard('Total', stats.total, '#1a365d')}
                {renderStatCard('Pending', stats.pending, '#f59e0b')}
                {renderStatCard('Received', stats.received, '#10b981')}
                {renderStatCard('Released', stats.released, '#3b82f6')}
              </View>
              <View style={styles.statsGrid}>
                {renderStatCard('In Review', stats.in_review, '#8b5cf6')}
                {renderStatCard('Routed', stats.routed, '#ec4899')}
                {renderStatCard('Transferred', stats.transferred, '#06b6d4')}
                {renderStatCard('On Hold', stats.on_hold, '#ef4444')}
              </View>
            </View>
          ) : null
        }
        contentContainerStyle={styles.listContent}
      />
    </SafeAreaView>
  );
}

function getStatusStyle(status: string) {
  switch (status) {
    case 'Pending':
      return { backgroundColor: '#fef3c7', color: '#92400e' };
    case 'Received':
      return { backgroundColor: '#d1fae5', color: '#065f46' };
    case 'Released':
      return { backgroundColor: '#dbeafe', color: '#1e40af' };
    case 'In Review':
      return { backgroundColor: '#ede9fe', color: '#5b21b6' };
    case 'On Hold':
      return { backgroundColor: '#fee2e2', color: '#991b1b' };
    default:
      return { backgroundColor: '#f3f4f6', color: '#374151' };
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f3f4f6',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    backgroundColor: '#1a365d',
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#fff',
  },
  logoutBtn: {
    padding: 8,
  },
  logoutText: {
    color: '#fff',
    fontSize: 14,
  },
  listContent: {
    padding: 16,
  },
  statsContainer: {
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 12,
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginBottom: 8,
  },
  statCard: {
    width: '48%',
    backgroundColor: '#fff',
    borderRadius: 8,
    padding: 16,
    marginBottom: 8,
    marginRight: '4%',
    borderLeftWidth: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  statValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#1f2937',
  },
  statTitle: {
    fontSize: 12,
    color: '#6b7280',
    marginTop: 4,
  },
  docItem: {
    backgroundColor: '#fff',
    borderRadius: 8,
    padding: 16,
    marginBottom: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  docHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  docRef: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1a365d',
  },
  docStatus: {
    fontSize: 12,
    fontWeight: '500',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
    overflow: 'hidden',
  },
  docSubject: {
    fontSize: 16,
    color: '#1f2937',
    marginBottom: 4,
  },
  docOffice: {
    fontSize: 12,
    color: '#6b7280',
  },
});