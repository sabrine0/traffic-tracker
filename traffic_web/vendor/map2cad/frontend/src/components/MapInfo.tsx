import { useState } from "react";
import { useMapEvents } from "react-leaflet";

export default function MapInfo() {
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);

  useMapEvents({
    mousemove(e) {
      setCoords({ lat: e.latlng.lat, lng: e.latlng.lng });
    },
    mouseout() {
      setCoords(null);
    },
  });

  if (!coords) return null;

  return (
    <div className="absolute bottom-2 right-2 z-[1000] rounded bg-white/90 px-2 py-1 text-xs text-gray-700 shadow">
      {coords.lat.toFixed(6)}, {coords.lng.toFixed(6)}
    </div>
  );
}
