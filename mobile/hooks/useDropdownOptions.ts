import { useQuery } from '@tanstack/react-query';
import api from '../lib/api';

export function useDropdownOptions() {
  return useQuery<Record<string, string[]>>({
    queryKey: ['dropdown-options'],
    queryFn: async () => {
      try {
        const res = await api.get('/dropdown-options');
        const raw: Record<string, unknown> = res.data ?? {};
        // Normalize both formats:
        //   flat:   { category: ["Letter", ...] }
        //   nested: { category: { options: ["Letter", ...], ... } }
        const normalized: Record<string, string[]> = {};
        for (const [key, val] of Object.entries(raw)) {
          if (Array.isArray(val)) {
            normalized[key] = val as string[];
          } else if (val && typeof val === 'object' && Array.isArray((val as any).options)) {
            normalized[key] = (val as any).options as string[];
          }
        }
        return normalized;
      } catch {
        return {};
      }
    },
    staleTime: 1000 * 60 * 30,
    retry: false,
  });
}

export function useOffices() {
  return useQuery<Array<{ office_name: string; office_slug: string }>>({
    queryKey: ['offices'],
    queryFn: async () => {
      try {
        const res = await api.get('/offices');
        return (res.data ?? []) as Array<{ office_name: string; office_slug: string }>;
      } catch {
        return [];
      }
    },
    staleTime: 1000 * 60 * 30,
    retry: false,
  });
}

export function useStaff() {
  return useQuery<Array<{ username: string; full_name: string; office: string; role: string }>>({
    queryKey: ['staff'],
    queryFn: async () => {
      try {
        const res = await api.get('/staff');
        return (res.data ?? []) as Array<{ username: string; full_name: string; office: string; role: string }>;
      } catch {
        return [];
      }
    },
    staleTime: 1000 * 60 * 30,
    retry: false,
  });
}

export function usePendingCount() {
  return useQuery<number>({
    queryKey: ['pending-count'],
    queryFn: async () => {
      try {
        const res = await api.get('/pending-count');
        return (res.data?.count ?? 0) as number;
      } catch {
        return 0;
      }
    },
    staleTime: 1000 * 60 * 2,
    refetchInterval: 1000 * 60 * 2,
    retry: false,
  });
}
