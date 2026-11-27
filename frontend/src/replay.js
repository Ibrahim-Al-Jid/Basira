// Replay of a stored scan (P20): pure timing logic, no React, no network.
// Events keep their stored order. Gaps come from the stored timestamps, scaled by speed and
// clamped so a long wait in the original run never stalls the demo and a burst stays readable.
export const SPEEDS = [1, 2, 4];
export const MIN_GAP_MS = 350;
export const MAX_GAP_MS = 1800;

export function gapAfter(previous, next, speed = 1) {
  const real = Date.parse(next.occurred_at) - Date.parse(previous.occurred_at);
  const scaled = (Number.isFinite(real) && real > 0 ? real : 0) / Math.max(1, speed);
  return Math.round(Math.min(MAX_GAP_MS, Math.max(MIN_GAP_MS / Math.max(1, speed), scaled)));
}

// Delay before each event is shown; the first one appears after one short beat.
export function replayDelays(events, speed = 1) {
  return events.map((item, index) => (index === 0 ? Math.round(MIN_GAP_MS / Math.max(1, speed)) : gapAfter(events[index - 1], item, speed)));
}

export function replayTotalMs(events, speed = 1) {
  return replayDelays(events, speed).reduce((sum, value) => sum + value, 0);
}

export function canReplay(scan, events) {
  return Boolean(scan) && !["queued", "running"].includes(scan.state) && events.length > 0;
}
