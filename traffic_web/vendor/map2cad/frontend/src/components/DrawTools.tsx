import { useEffect, useRef, useCallback } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet-draw";
import "leaflet-draw/dist/leaflet.draw.css";
import { useSelection } from "../context/SelectionContext";
import { isAreaTooLarge, geodesicArea } from "../utils/geometry";
import type { LatLngTuple } from "leaflet";

const NORMAL_STYLE: L.PathOptions = {
  color: "#2563eb",
  fillColor: "#3b82f6",
  fillOpacity: 0.12,
  weight: 2.5,
  dashArray: "8 5",
  opacity: 0.9,
};

const NORMAL_HOVER_STYLE: L.PathOptions = {
  ...NORMAL_STYLE,
  fillOpacity: 0.22,
  weight: 3,
  opacity: 1,
};

const OVER_LIMIT_STYLE: L.PathOptions = {
  color: "#dc2626",
  fillColor: "#ef4444",
  fillOpacity: 0.12,
  weight: 2.5,
  dashArray: "8 5",
  opacity: 0.9,
};

const OVER_LIMIT_HOVER_STYLE: L.PathOptions = {
  ...OVER_LIMIT_STYLE,
  fillOpacity: 0.22,
  weight: 3,
  opacity: 1,
};

function layerToCoords(layer: L.Layer): LatLngTuple[] {
  const latlngs = (layer as L.Polygon).getLatLngs()[0] as L.LatLng[];
  return latlngs.map((ll) => [ll.lat, ll.lng] as LatLngTuple);
}

export default function DrawTools() {
  const map = useMap();
  const { setSelection, clearSelection } = useSelection();
  const drawnLayerRef = useRef<L.FeatureGroup>(new L.FeatureGroup());
  const drawControlRef = useRef<L.Control.Draw | null>(null);

  const updateStyle = useCallback((layer: L.Layer) => {
    const coords = layerToCoords(layer);
    const area = geodesicArea(coords);
    const overLimit = isAreaTooLarge(area);
    (layer as L.Polygon).setStyle(overLimit ? OVER_LIMIT_STYLE : NORMAL_STYLE);

    (layer as L.Polygon).off("mouseover mouseout");
    (layer as L.Polygon).on("mouseover", () => {
      (layer as L.Polygon).setStyle(overLimit ? OVER_LIMIT_HOVER_STYLE : NORMAL_HOVER_STYLE);
    });
    (layer as L.Polygon).on("mouseout", () => {
      (layer as L.Polygon).setStyle(overLimit ? OVER_LIMIT_STYLE : NORMAL_STYLE);
    });
  }, []);

  useEffect(() => {
    const drawnItems = drawnLayerRef.current;
    map.addLayer(drawnItems);

    const drawControl = new L.Control.Draw({
      position: "topleft",
      draw: {
        polygon: { shapeOptions: NORMAL_STYLE, allowIntersection: false },
        rectangle: { shapeOptions: NORMAL_STYLE },
        circle: false,
        circlemarker: false,
        marker: false,
        polyline: false,
      },
      edit: {
        featureGroup: drawnItems,
        remove: true,
      },
    });

    map.addControl(drawControl);
    drawControlRef.current = drawControl;

    function onCreated(e: L.LeafletEvent) {
      const event = e as L.DrawEvents.Created;
      drawnItems.clearLayers();
      drawnItems.addLayer(event.layer);

      const coords = layerToCoords(event.layer);
      const selType = event.layerType === "rectangle" ? "rectangle" : "polygon";
      setSelection(coords, selType);
      updateStyle(event.layer);
    }

    function onEdited(e: L.LeafletEvent) {
      const event = e as L.DrawEvents.Edited;
      event.layers.eachLayer((layer) => {
        const coords = layerToCoords(layer);
        setSelection(coords, coords.length === 4 ? "rectangle" : "polygon");
        updateStyle(layer);
      });
    }

    function onDeleted() {
      clearSelection();
    }

    map.on(L.Draw.Event.CREATED, onCreated);
    map.on(L.Draw.Event.EDITED, onEdited);
    map.on(L.Draw.Event.DELETED, onDeleted);

    return () => {
      map.off(L.Draw.Event.CREATED, onCreated);
      map.off(L.Draw.Event.EDITED, onEdited);
      map.off(L.Draw.Event.DELETED, onDeleted);
      map.removeControl(drawControl);
      map.removeLayer(drawnItems);
    };
  }, [map, setSelection, clearSelection, updateStyle]);

  return null;
}
