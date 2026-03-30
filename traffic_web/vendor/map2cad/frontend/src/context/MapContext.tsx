import { createContext, useContext, useState, useCallback } from "react";
import type { LatLngBoundsLiteral, LatLngTuple } from "leaflet";

interface MapState {
  center: LatLngTuple;
  zoom: number;
  bounds: LatLngBoundsLiteral | null;
}

interface MapContextValue extends MapState {
  setCenter: (center: LatLngTuple) => void;
  setZoom: (zoom: number) => void;
  setBounds: (bounds: LatLngBoundsLiteral) => void;
  flyTo: (center: LatLngTuple, zoom?: number) => void;
  pendingFly: { center: LatLngTuple; zoom: number } | null;
  clearPendingFly: () => void;
}

const MapContext = createContext<MapContextValue | null>(null);

export function MapProvider({ children }: { children: React.ReactNode }) {
  const [center, setCenter] = useState<LatLngTuple>([33.5731, -7.5898]);
  const [zoom, setZoom] = useState(13);
  const [bounds, setBounds] = useState<LatLngBoundsLiteral | null>(null);
  const [pendingFly, setPendingFly] = useState<{ center: LatLngTuple; zoom: number } | null>(null);

  const flyTo = useCallback((target: LatLngTuple, targetZoom = 16) => {
    setPendingFly({ center: target, zoom: targetZoom });
  }, []);

  const clearPendingFly = useCallback(() => {
    setPendingFly(null);
  }, []);

  return (
    <MapContext.Provider
      value={{ center, zoom, bounds, setCenter, setZoom, setBounds, flyTo, pendingFly, clearPendingFly }}
    >
      {children}
    </MapContext.Provider>
  );
}

export function useMapContext() {
  const ctx = useContext(MapContext);
  if (!ctx) throw new Error("useMapContext must be used within MapProvider");
  return ctx;
}
