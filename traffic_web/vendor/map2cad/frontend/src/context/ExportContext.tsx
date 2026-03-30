import { createContext, useContext, useState, useCallback } from "react";

export type CrsOption = "utm" | "lambert93" | "lambert_nord" | "lambert_sud" | "lambert_cc46" | "lambert_cc47";

export interface ExportOptions {
  // Road layers
  lane_markings: boolean;
  sidewalks: boolean;
  curbs: boolean;
  intersections: boolean;
  road_names: boolean;
  // Feature layers
  buildings: boolean;
  landuse: boolean;
  railways: boolean;
  parking: boolean;
  traffic_signals: boolean;
  street_furniture: boolean;
  cycling: boolean;
  utilities: boolean;
  // CRS
  crs: CrsOption;
}

const DEFAULT_OPTIONS: ExportOptions = {
  lane_markings: true,
  sidewalks: true,
  curbs: true,
  intersections: true,
  road_names: true,
  buildings: false,
  landuse: false,
  railways: false,
  parking: false,
  traffic_signals: false,
  street_furniture: false,
  cycling: false,
  utilities: false,
  crs: "utm",
};

interface ExportContextValue {
  options: ExportOptions;
  setOption: (key: keyof ExportOptions, value: boolean) => void;
  setCrs: (crs: CrsOption) => void;
  resetOptions: () => void;
}

const ExportContext = createContext<ExportContextValue | null>(null);

export function ExportProvider({ children }: { children: React.ReactNode }) {
  const [options, setOptions] = useState<ExportOptions>(DEFAULT_OPTIONS);

  const setOption = useCallback((key: keyof ExportOptions, value: boolean) => {
    setOptions((prev) => ({ ...prev, [key]: value }));
  }, []);

  const setCrs = useCallback((crs: CrsOption) => {
    setOptions((prev) => ({ ...prev, crs }));
  }, []);

  const resetOptions = useCallback(() => {
    setOptions(DEFAULT_OPTIONS);
  }, []);

  return (
    <ExportContext.Provider value={{ options, setOption, setCrs, resetOptions }}>
      {children}
    </ExportContext.Provider>
  );
}

export function useExportOptions() {
  const ctx = useContext(ExportContext);
  if (!ctx) throw new Error("useExportOptions must be used within ExportProvider");
  return ctx;
}
