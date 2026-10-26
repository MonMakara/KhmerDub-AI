/**
 * Cambodia Timezone (Asia/Phnom_Penh, UTC+7) Date & Time Utilities.
 * Ensures consistent rendering of Cambodian local time across all platforms and browsers.
 */

export const CAMBODIA_TIMEZONE = 'Asia/Phnom_Penh';

/**
 * Safely parses any date representation (ISO string, SQLite string, epoch ms, or Date object)
 * into a Date object correctly aligned with Cambodia Time.
 */
export function parseCambodiaDate(input: string | number | Date | null | undefined): Date | null {
  if (!input) return null;
  if (input instanceof Date) return isNaN(input.getTime()) ? null : input;
  if (typeof input === 'number') {
    const d = new Date(input);
    return isNaN(d.getTime()) ? null : d;
  }

  let str = String(input).trim();
  if (!str) return null;

  // If the string contains a date-time without timezone offset or Z suffix,
  // interpret it as Cambodia local time (+07:00).
  if (/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(str) && !/(?:Z|[+-]\d{2}(?::?\d{2})?)$/i.test(str)) {
    str = str.replace(' ', 'T') + '+07:00';
  }

  const d = new Date(str);
  return isNaN(d.getTime()) ? null : d;
}

/**
 * Formats a date into a localized date string in Cambodia Time (e.g. "10/26/2026").
 */
export function formatCambodiaDate(
  input: string | number | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions
): string {
  const date = parseCambodiaDate(input);
  if (!date) return '';

  const defaultOptions: Intl.DateTimeFormatOptions = {
    timeZone: CAMBODIA_TIMEZONE,
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    ...options,
  };

  return new Intl.DateTimeFormat('en-US', defaultOptions).format(date);
}

/**
 * Formats a date into a localized 12-hour time string in Cambodia Time (e.g. "02:05 PM").
 */
export function formatCambodiaTime(
  input: string | number | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions
): string {
  const date = parseCambodiaDate(input);
  if (!date) return '';

  const defaultOptions: Intl.DateTimeFormatOptions = {
    timeZone: CAMBODIA_TIMEZONE,
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
    ...options,
  };

  return new Intl.DateTimeFormat('en-US', defaultOptions).format(date);
}

/**
 * Formats a date into full localized date and time in Cambodia Time (e.g. "10/26/2026, 02:05 PM").
 */
export function formatCambodiaDateTime(
  input: string | number | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions
): string {
  const date = parseCambodiaDate(input);
  if (!date) return '';

  const defaultOptions: Intl.DateTimeFormatOptions = {
    timeZone: CAMBODIA_TIMEZONE,
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
    ...options,
  };

  return new Intl.DateTimeFormat('en-US', defaultOptions).format(date);
}
