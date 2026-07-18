declare global {
  interface WakeLockSentinel extends EventTarget {
    released: boolean;
    release(): Promise<void>;
  }

  interface Navigator {
    wakeLock?: {
      request(type: 'screen'): Promise<WakeLockSentinel>;
    };
  }
}

export {};

