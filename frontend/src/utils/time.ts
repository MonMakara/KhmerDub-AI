/**
 * Precise Time and Duration Utilities for KhmerDub AI Media Trimming Studio.
 * Supports millisecond-precision timestamps (HH:MM:SS.mmm).
 */

/**
 * Parses a timestamp string (HH:MM:SS.mmm, MM:SS.mmm, SS.mmm) or numeric seconds into float seconds.
 * Returns NaN if string syntax is invalid or negative.
 */
export function parseTimestamp(val: string | number | null | undefined): number {
  if (val === null || val === undefined) return NaN;
  if (typeof val === 'number') {
    return val >= 0 ? Number(val.toFixed(3)) : NaN;
  }

  const s = String(val).trim();
  if (!s || s.startsWith('-')) return NaN;

  const parts = s.split(':');
  try {
    let seconds = 0;
    if (parts.length === 3) {
      const [h, m, sec] = parts;
      if (isNaN(Number(h)) || isNaN(Number(m)) || isNaN(Number(sec))) return NaN;
      seconds = parseInt(h, 10) * 3600 + parseInt(m, 10) * 60 + parseFloat(sec);
    } else if (parts.length === 2) {
      const [m, sec] = parts;
      if (isNaN(Number(m)) || isNaN(Number(sec))) return NaN;
      seconds = parseInt(m, 10) * 60 + parseFloat(sec);
    } else if (parts.length === 1) {
      if (isNaN(Number(parts[0]))) return NaN;
      seconds = parseFloat(parts[0]);
    } else {
      return NaN;
    }

    return seconds >= 0 ? Math.round(seconds * 1000) / 1000 : NaN;
  } catch {
    return NaN;
  }
}

/**
 * Formats seconds into HH:MM:SS.mmm representation with millisecond precision.
 * Example: 75.25 -> "00:01:15.250"
 */
export function formatTimestamp(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || isNaN(seconds) || seconds < 0) {
    return '00:00:00.000';
  }

  const totalMs = Math.round(seconds * 1000);
  const ms = totalMs % 1000;
  const totalSec = Math.floor(totalMs / 1000);
  const s = totalSec % 60;
  const m = Math.floor((totalSec % 3600) / 60);
  const h = Math.floor(totalSec / 3600);

  const pad = (n: number, z = 2) => String(n).padStart(z, '0');

  return `${pad(h)}:${pad(m)}:${pad(s)}.${pad(ms, 3)}`;
}

/**
 * Formats a short duration string for display badges (e.g. "01:15.2" or "2m 15s").
 */
export function formatShortDuration(seconds: number | null | undefined): string {
  if (!seconds || isNaN(seconds) || seconds <= 0) return '0.0s';
  if (seconds < 60) return `${seconds.toFixed(2)}s`;
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(1);
  return `${m}m ${s}s`;
}

/**
 * Clamps a number between min and max.
 */
export function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(val, max));
}
