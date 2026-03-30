import { createContext, useContext, useState, useCallback } from "react";
import type { LatLngTuple } from "leaflet";

export type SelectionType = "rectangle" | "polygon" | null;

interface SelectionState {
  coords: LatLngTuple[] | null;
  type: SelectionType;
}

interface SelectionContextValue extends SelectionState {
  setSelection: (coords: LatLngTuple[] | null, type: SelectionType) => void;
  clearSelection: () => void;
}

const SelectionContext = createContext<SelectionContextValue | null>(null);

export function SelectionProvider({ children }: { children: React.ReactNode }) {
  const [coords, setCoords] = useState<LatLngTuple[] | null>(null);
  const [type, setType] = useState<SelectionType>(null);

  const setSelection = useCallback((newCoords: LatLngTuple[] | null, newType: SelectionType) => {
    setCoords(newCoords);
    setType(newType);
  }, []);

  const clearSelection = useCallback(() => {
    setCoords(null);
    setType(null);
  }, []);

  return (
    <SelectionContext.Provider value={{ coords, type, setSelection, clearSelection }}>
      {children}
    </SelectionContext.Provider>
  );
}

export function useSelection() {
  const ctx = useContext(SelectionContext);
  if (!ctx) throw new Error("useSelection must be used within SelectionProvider");
  return ctx;
}
