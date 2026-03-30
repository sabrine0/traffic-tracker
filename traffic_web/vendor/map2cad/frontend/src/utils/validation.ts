import type { LatLngTuple } from "leaflet";
import { geodesicArea, isAreaTooLarge } from "./geometry";

export interface ValidationResult {
  valid: boolean;
  error: string | null;
}

export function validatePolygon(coords: LatLngTuple[] | null): ValidationResult {
  if (!coords || coords.length === 0) {
    return { valid: false, error: "No area selected. Draw a polygon or rectangle on the map." };
  }

  if (coords.length < 3) {
    return { valid: false, error: "Selection must have at least 3 vertices." };
  }

  for (let i = 0; i < coords.length; i++) {
    const [lat, lng] = coords[i];
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      return { valid: false, error: `Invalid coordinate at vertex ${i + 1}.` };
    }
    if (lat < -90 || lat > 90) {
      return { valid: false, error: `Latitude out of range at vertex ${i + 1}.` };
    }
    if (lng < -180 || lng > 180) {
      return { valid: false, error: `Longitude out of range at vertex ${i + 1}.` };
    }
  }

  const area = geodesicArea(coords);
  if (isAreaTooLarge(area)) {
    return { valid: false, error: "Selected area exceeds the 25 km² limit. Please select a smaller region." };
  }

  return { valid: true, error: null };
}
