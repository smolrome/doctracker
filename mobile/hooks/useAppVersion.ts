/**
 * useAppVersion
 *
 * Fetches /api/app-version from the server and compares it with the
 * version declared in app.json (via expo-constants).
 *
 * Returns:
 *   needsUpdate  — app is behind latest_version  (soft prompt)
 *   mustUpdate   — app is behind min_version      (hard block)
 *   downloadUrl  — where to send the user to update
 *   releaseNotes — what changed in the new version
 */

import { useEffect, useState } from 'react';
import Constants from 'expo-constants';
import api from '../lib/api';

interface VersionInfo {
  latest_version: string;
  min_version:    string;
  download_url:   string;
  release_notes:  string;
  force_update:   boolean;
}

interface AppVersionState {
  needsUpdate:  boolean;   // behind latest but above min
  mustUpdate:   boolean;   // below min — must update to continue
  downloadUrl:  string;
  releaseNotes: string;
  latestVersion: string;
  checked:      boolean;   // true once the check has completed
}

/** Compares two semver strings. Returns negative if a < b, 0 if equal, positive if a > b. */
function compareSemver(a: string, b: string): number {
  const parse = (v: string) =>
    String(v || '0.0.0').split('.').map((n) => parseInt(n, 10) || 0);
  const [aMaj, aMin, aPat] = parse(a);
  const [bMaj, bMin, bPat] = parse(b);
  if (aMaj !== bMaj) return aMaj - bMaj;
  if (aMin !== bMin) return aMin - bMin;
  return aPat - bPat;
}

export function useAppVersion(): AppVersionState {
  const currentVersion: string =
    (Constants.expoConfig?.version ?? Constants.manifest?.version ?? '0.0.0') as string;

  const [state, setState] = useState<AppVersionState>({
    needsUpdate:   false,
    mustUpdate:    false,
    downloadUrl:   '',
    releaseNotes:  '',
    latestVersion: '',
    checked:       false,
  });

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const res = await api.get<VersionInfo>('/app-version');
        const { latest_version, min_version, download_url, release_notes, force_update } = res.data;

        if (cancelled) return;

        const behindMin    = compareSemver(currentVersion, min_version)    < 0;
        const behindLatest = compareSemver(currentVersion, latest_version) < 0;

        setState({
          mustUpdate:    behindMin || force_update,
          needsUpdate:   !behindMin && behindLatest,
          downloadUrl:   download_url,
          releaseNotes:  release_notes,
          latestVersion: latest_version,
          checked:       true,
        });
      } catch {
        // Network error or server unavailable — don't block the app
        if (!cancelled) setState((s) => ({ ...s, checked: true }));
      }
    })();

    return () => { cancelled = true; };
  }, []);

  return state;
}
