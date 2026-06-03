/**
 * Display formatting helpers.
 *
 * The backend always stores SI units (meters, seconds) — that's the right call
 * for storage. We convert to imperial *only at the display edge*, here, so
 * there's a single place to change units later (or wire a per-user preference).
 */

const METERS_PER_MILE = 1609.344;

export function metersToMiles(meters: number): number {
  return meters / METERS_PER_MILE;
}

/** e.g. 10000 -> "6.2 mi". Returns "—" for null/undefined. */
export function formatMiles(meters: number | null | undefined, digits = 1): string {
  if (meters == null) return "—";
  return `${metersToMiles(meters).toFixed(digits)} mi`;
}

/** e.g. 3900 -> "1h 5m"; 2400 -> "40m". Returns "—" for null/undefined. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${seconds}s`;
}

/** Running pace in min/mile, e.g. "8:30 /mi". Needs both distance and time. */
export function formatPace(
  meters: number | null | undefined,
  seconds: number | null | undefined,
): string {
  if (!meters || !seconds) return "—";
  const miles = metersToMiles(meters);
  if (miles < 0.05) return "—"; // too short to be meaningful
  const secPerMile = seconds / miles;
  const m = Math.floor(secPerMile / 60);
  const s = Math.round(secPerMile % 60);
  return `${m}:${s.toString().padStart(2, "0")} /mi`;
}
