import axios from "axios";

export interface GeocodingResult {
  displayName: string;
  lat: number;
  lng: number;
  boundingBox: [number, number, number, number];
}

const NOMINATIM_URL = "https://nominatim.openstreetmap.org/search";

export async function searchLocation(query: string): Promise<GeocodingResult[]> {
  if (!query.trim()) return [];

  const response = await axios.get(NOMINATIM_URL, {
    params: {
      q: query,
      format: "json",
      limit: 5,
      addressdetails: 0,
    },
    headers: {
      "Accept-Language": "en",
    },
  });

  return response.data.map((item: { display_name: string; lat: string; lon: string; boundingbox: string[] }) => ({
    displayName: item.display_name,
    lat: parseFloat(item.lat),
    lng: parseFloat(item.lon),
    boundingBox: item.boundingbox.map(Number) as [number, number, number, number],
  }));
}
