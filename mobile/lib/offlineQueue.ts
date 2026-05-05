import AsyncStorage from '@react-native-async-storage/async-storage';

const QUEUE_KEY = 'doctracker-offline-submit-queue';
const MAX_RETRIES = 5;

export type QueuedSubmission = {
  queueId: string;
  payload: {
    office_slug: string;
    office_name: string;
    selected_staff: string;
    documents: {
      doc_name: string;
      referred_to: string;
      unit_office: string;
      category: string;
      description: string;
    }[];
  };
  queuedAt: number;   // epoch ms
  retries: number;
};

async function _read(): Promise<QueuedSubmission[]> {
  try {
    const raw = await AsyncStorage.getItem(QUEUE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

async function _write(queue: QueuedSubmission[]): Promise<void> {
  await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
}

export const offlineQueue = {
  /** Add a submission to the queue. Returns the generated queueId. */
  async enqueue(payload: QueuedSubmission['payload']): Promise<string> {
    const queueId = `Q-${Date.now()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
    const item: QueuedSubmission = { queueId, payload, queuedAt: Date.now(), retries: 0 };
    const queue = await _read();
    queue.push(item);
    await _write(queue);
    return queueId;
  },

  async getAll(): Promise<QueuedSubmission[]> {
    return _read();
  },

  async count(): Promise<number> {
    return (await _read()).length;
  },

  async remove(queueId: string): Promise<void> {
    const queue = await _read();
    await _write(queue.filter((i) => i.queueId !== queueId));
  },

  async incrementRetry(queueId: string): Promise<void> {
    const queue = await _read();
    const index = queue.findIndex((i) => i.queueId === queueId);
    if (index === -1) return;
    queue[index].retries += 1;
    if (queue[index].retries >= MAX_RETRIES) {
      queue.splice(index, 1);
    }
    await _write(queue);
  },

  async clear(): Promise<void> {
    await AsyncStorage.removeItem(QUEUE_KEY);
  },
};
