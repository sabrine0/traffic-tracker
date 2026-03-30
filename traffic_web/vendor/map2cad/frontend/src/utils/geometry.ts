import type { LatLngTuple } from "leaflet";

const EARTH_RADIUS = 6371000; // meters

function toRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

/**
 * Calculate geodesic area of a polygon using the spherical excess formula.
 * Coordinates are [lat, lng] (LatLngTuple). Returns area in square meters.
 */
export function geodesicArea(coords: LatLngTuple[]): number {
  if (coords.length < 3) return 0;

  let total = 0;
  const n = coords.length;

  for (let i = 0; i < n; i++) {
    const [lat1, lng1] = coords[i];
    const [lat2, lng2] = coords[(i + 1) % n];

    total +=
      toRad(lng2 - lng1) *
      (2 + Math.sin(toRad(lat1)) + Math.sin(toRad(lat2)));
  }

  return Math.abs((total * EARTH_RADIUS * EARTH_RADIUS) / 2);
}

/**
 * Format area with appropriate units.
 */
export function formatArea(areaM2: number): string {
  if (areaM2 < 1_000_000) {
    return `${Math.round(areaM2).toLocaleString()} m\u00B2`;
  }
  return `${(areaM2 / 1_000_000).toFixed(2)} km\u00B2`;
}

/**
 * Maximum selection area in square meters (default 25 km²).
 */
export const MAX_AREA_M2 = 25_000_000;

/**
 * Check if area exceeds the limit.
 */
export function isAreaTooLarge(areaM2: number): boolean {
  return areaM2 > MAX_AREA_M2;
}
