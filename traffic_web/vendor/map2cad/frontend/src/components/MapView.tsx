import { useEffect, useRef } from "react";
import { MapContainer, TileLayer, ScaleControl, LayersControl, useMapEvents, useMap } from "react-leaflet";
import { useMapContext } from "../context/MapContext";
import type { LatLngTuple } from "leaflet";
import "leaflet/dist/leaflet.css";
import MapInfo from "./MapInfo";
import DrawTools from "./DrawTools";

function MapEventHandler() {
  const { setCenter, setZoom, setBounds } = useMapContext();

  useMapEvents({
    moveend(e) {
      const map = e.target;
      const c = map.getCenter();
      setCenter([c.lat, c.lng]);
      setZoom(map.getZoom());
      const b = map.getBounds();
      setBounds([
        [b.getSouth(), b.getWest()],
        [b.getNorth(), b.getEast()],
      ]);
    },
    zoomend(e) {
      setZoom(e.target.getZoom());
    },
  });

  return null;
}

function FlyHandler() {
  const map = useMap();
  const { pendingFly, clearPendingFly } = useMapContext();

  useEffect(() => {
    if (pendingFly) {
      map.flyTo(pendingFly.center, pendingFly.zoom, { duration: 1.5 });
      clearPendingFly();
    }
  }, [pendingFly, map, clearPendingFly]);

  return null;
}

function ResizeHandler() {
  const map = useMap();
  const containerRef = useRef(map.getContainer());

  useEffect(() => {
    const observer = new ResizeObserver(() => {
      map.invalidateSize();
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [map]);

  return null;
}

const TILE_LAYERS = {
  street: {
    name: "Street",
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  },
  satellite: {
    name: "Satellite",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "&copy; Esri &mdash; Earthstar Geographics",
  },
  terrain: {
    name: "Terrain",
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://opentopomap.org">OpenTopoMap</a> contributors',
  },
};

interface MapViewProps {
  defaultCenter?: LatLngTuple;
  defaultZoom?: number;
}

export default function MapView({ defaultCenter = [33.5731, -7.5898], defaultZoom = 13 }: MapViewProps) {
  return (
    <div className="relative h-full w-full map-container">
      <MapContainer
        center={defaultCenter}
        zoom={defaultZoom}
        className="h-full w-full z-0"
        zoomControl={true}
        scrollWheelZoom={true}
        doubleClickZoom={true}
        dragging={true}
        zoomAnimation={true}
        fadeAnimation={true}
        markerZoomAnimation={true}
      >
        <LayersControl position="topright">
          <LayersControl.BaseLayer checked name={TILE_LAYERS.street.name}>
            <TileLayer url={TILE_LAYERS.street.url} attribution={TILE_LAYERS.street.attribution} />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name={TILE_LAYERS.satellite.name}>
            <TileLayer url={TILE_LAYERS.satellite.url} attribution={TILE_LAYERS.satellite.attribution} />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name={TILE_LAYERS.terrain.name}>
            <TileLayer url={TILE_LAYERS.terrain.url} attribution={TILE_LAYERS.terrain.attribution} />
          </LayersControl.BaseLayer>
        </LayersControl>

        <ScaleControl position="bottomleft" imperial={false} />
        <MapEventHandler />
        <FlyHandler />
        <ResizeHandler />
        <MapInfo />
        <DrawTools />
      </MapContainer>
    </div>
  );
}
