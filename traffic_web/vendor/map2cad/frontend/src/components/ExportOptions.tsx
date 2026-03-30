import { useExportOptions, type ExportOptions, type CrsOption } from "../context/ExportContext";

interface ToggleGroup {
  title: string;
  keys: (keyof ExportOptions)[];
}

const TOGGLE_LABELS: Record<string, { label: string; tooltip: string }> = {
  // Road layers
  lane_markings: {
    label: "Lane Markings",
    tooltip: "Dashed/solid lane dividers between lanes",
  },
  sidewalks: {
    label: "Sidewalks",
    tooltip: "Pedestrian sidewalk outlines along roads",
  },
  curbs: {
    label: "Curbs",
    tooltip: "Curb lines between road edge and sidewalk",
  },
  intersections: {
    label: "Intersections",
    tooltip: "Intersection polygons with turning radii",
  },
  road_names: {
    label: "Road Names",
    tooltip: "Text labels along road centerlines",
  },
  // Structures
  buildings: {
    label: "Buildings",
    tooltip: "Building footprint outlines",
  },
  landuse: {
    label: "Land Use",
    tooltip: "Parks, water bodies, industrial/commercial/residential zones",
  },
  parking: {
    label: "Parking",
    tooltip: "Parking lots and on-street parking spaces",
  },
  // Infrastructure
  railways: {
    label: "Railways",
    tooltip: "Rail lines, tram tracks, light rail, subway",
  },
  cycling: {
    label: "Cycling",
    tooltip: "Bike lanes and cycling paths",
  },
  utilities: {
    label: "Utilities",
    tooltip: "Power lines and manholes",
  },
  // Street details
  traffic_signals: {
    label: "Traffic Signals",
    tooltip: "Traffic signal locations",
  },
  street_furniture: {
    label: "Street Furniture",
    tooltip: "Trees, benches, and street lights",
  },
};

const TOGGLE_GROUPS: ToggleGroup[] = [
  {
    title: "Road Layers",
    keys: ["lane_markings", "sidewalks", "curbs", "intersections", "road_names"],
  },
  {
    title: "Structures",
    keys: ["buildings", "landuse", "parking"],
  },
  {
    title: "Infrastructure",
    keys: ["railways", "cycling", "utilities"],
  },
  {
    title: "Street Details",
    keys: ["traffic_signals", "street_furniture"],
  },
];

const CRS_OPTIONS: { value: CrsOption; label: string }[] = [
  { value: "utm", label: "UTM (auto-detect)" },
  { value: "lambert93", label: "Lambert-93 (France)" },
  { value: "lambert_nord", label: "Lambert Nord (France legacy)" },
  { value: "lambert_sud", label: "Lambert Sud (France legacy)" },
  { value: "lambert_cc46", label: "Lambert CC46" },
  { value: "lambert_cc47", label: "Lambert CC47" },
];

export default function ExportOptionsPanel() {
  const { options, setOption, setCrs } = useExportOptions();

  return (
    <div className="space-y-3">
      {/* CRS selector */}
      <div>
        <label htmlFor="crs-select" className="text-xs font-medium text-gray-500 uppercase tracking-wider">
          Coordinate System
        </label>
        <select
          id="crs-select"
          value={options.crs}
          onChange={(e) => setCrs(e.target.value as CrsOption)}
          className="mt-1.5 w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
        >
          {CRS_OPTIONS.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </div>

      {/* Toggle groups */}
      {TOGGLE_GROUPS.map((group) => (
        <div key={group.title}>
          <div className="border-t border-gray-100 pt-2">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">{group.title}</span>
          </div>

          {group.keys.map((key) => {
            const meta = TOGGLE_LABELS[key];
            return (
              <label
                key={key}
                className="flex items-center justify-between gap-2 rounded px-2 py-1.5 hover:bg-gray-50 cursor-pointer group"
                title={meta.tooltip}
              >
                <span className="text-sm text-gray-700 select-none">{meta.label}</span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={options[key] as boolean}
                  aria-label={`Toggle ${meta.label}`}
                  onClick={() => setOption(key, !(options[key] as boolean))}
                  className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors duration-200 ${
                    options[key] ? "bg-blue-600" : "bg-gray-300"
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-4 w-4 translate-y-0.5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                      options[key] ? "translate-x-4.5" : "translate-x-0.5"
                    }`}
                  />
                </button>
              </label>
            );
          })}
        </div>
      ))}
    </div>
  );
}
