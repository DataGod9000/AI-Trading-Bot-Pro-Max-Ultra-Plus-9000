export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function randInt(min: number, max: number): number {
  const lo = Math.ceil(min);
  const hi = Math.floor(max);
  return Math.floor(lo + Math.random() * (hi - lo + 1));
}

export function isSnapshotModeClient(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.sessionStorage.getItem("btc_snapshot_mode") === "1";
  } catch {
    return false;
  }
}

/**
 * Add a tiny delay to smooth perception in snapshot mode.
 * Default: 200–800ms randomized.
 */
export async function snapshotDelay(minMs = 200, maxMs = 800): Promise<void> {
  if (!isSnapshotModeClient()) return;
  await sleep(randInt(minMs, maxMs));
}

