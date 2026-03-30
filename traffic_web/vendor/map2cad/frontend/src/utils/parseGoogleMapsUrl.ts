export interface ParsedMapLocation {
  lat: number;
  lng: number;
  zoom?: number;
}

const GOOGLE_MAPS_RE = /google\.[a-z.]+\/maps|maps\.google\.[a-z.]+/i;
const SHORT_LINK_RE = /goo\.gl\/maps|maps\.app\.goo\.gl/i;
const AT_PATTERN = /@(-?\d+\.?\d*),(-?\d+\.?\d*),(\d+\.?\d*)z/;
const Q_OR_LL_PATTERN = /[?&](?:q|ll)=(-?\d+\.?\d*),(-?\d+\.?\d*)/;
const ZOOM_PARAM_PATTERN = /[?&]z=(\d+\.?\d*)/;

export function isGoogleMapsUrl(input: string): boolean {
  const trimmed = input.trim();
  return GOOGLE_MAPS_RE.test(trimmed) || SHORT_LINK_RE.test(trimmed);
}

export function isShortLink(input: string): boolean {
  return SHORT_LINK_RE.test(input.trim());
}

export function parseGoogleMapsUrl(input: string): ParsedMapLocation | null {
  const trimmed = input.trim();

  if (!GOOGLE_MAPS_RE.test(trimmed)) return null;
  if (SHORT_LINK_RE.test(trimmed)) return null;

  // Try /@lat,lng,zoomz pattern
  const atMatch = trimmed.match(AT_PATTERN);
  if (atMatch) {
    const lat = parseFloat(atMatch[1]);
    const lng = parseFloat(atMatch[2]);
    const zoom = parseFloat(atMatch[3]);
    if (isValidCoords(lat, lng)) {
      return { lat, lng, zoom: Math.round(zoom) };
    }
  }

  // Try ?q=lat,lng or ?ll=lat,lng pattern
  const qMatch = trimmed.match(Q_OR_LL_PATTERN);
  if (qMatch) {
    const lat = parseFloat(qMatch[1]);
    const lng = parseFloat(qMatch[2]);
    if (isValidCoords(lat, lng)) {
      const zoomMatch = trimmed.match(ZOOM_PARAM_PATTERN);
      const zoom = zoomMatch ? Math.round(parseFloat(zoomMatch[1])) : undefined;
      return { lat, lng, zoom };
    }
  }

  return null;
}

function isValidCoords(lat: number, lng: number): boolean {
  return (
    !isNaN(lat) &&
    !isNaN(lng) &&
    lat >= -90 &&
    lat <= 90 &&
    lng >= -180 &&
    lng <= 180
  );
}
