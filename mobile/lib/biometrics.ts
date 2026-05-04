/**
 * Safe wrapper around expo-local-authentication.
 * Returns graceful fallbacks if the native module isn't available
 * (e.g., running in Expo Go without a native rebuild).
 */

let LocalAuth: typeof import('expo-local-authentication') | null = null;
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  LocalAuth = require('expo-local-authentication');
} catch {
  // Native module not available (Expo Go without rebuild)
}

export async function hasHardwareAsync(): Promise<boolean> {
  try {
    return (await LocalAuth?.hasHardwareAsync()) ?? false;
  } catch {
    return false;
  }
}

export async function isEnrolledAsync(): Promise<boolean> {
  try {
    return (await LocalAuth?.isEnrolledAsync()) ?? false;
  } catch {
    return false;
  }
}

export async function authenticateAsync(
  options?: { promptMessage?: string; cancelLabel?: string; fallbackLabel?: string }
): Promise<{ success: boolean; error?: string; warning?: string }> {
  try {
    return (await LocalAuth?.authenticateAsync(options)) ?? { success: false };
  } catch {
    return { success: false };
  }
}
