import { useSelection } from "../context/SelectionContext";
import { geodesicArea, formatArea, isAreaTooLarge, MAX_AREA_M2 } from "../utils/geometry";

export default function SelectionInfo() {
  const { coords, type, clearSelection } = useSelection();

  if (!coords) {
    return <p className="text-sm text-gray-400">No area selected</p>;
  }

  const area = geodesicArea(coords);
  const tooLarge = isAreaTooLarge(area);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-500 uppercase">
          {type === "rectangle" ? "Rectangle" : "Polygon"} ({coords.length} vertices)
        </span>
        <button
          onClick={clearSelection}
          className="text-xs text-red-500 hover:text-red-700"
        >
          Clear
        </button>
      </div>

      <div className={`rounded px-3 py-2 text-sm font-medium ${tooLarge ? "bg-red-50 text-red-700" : "bg-blue-50 text-blue-700"}`}>
        Area: {formatArea(area)}
      </div>

      {tooLarge && (
        <p className="text-xs text-red-600">
          Exceeds max area of {formatArea(MAX_AREA_M2)}. Reduce selection to export.
        </p>
      )}

      <details className="text-xs text-gray-500">
        <summary className="cursor-pointer hover:text-gray-700">Coordinates</summary>
        <ul className="mt-1 max-h-32 overflow-y-auto space-y-0.5 font-mono">
          {coords.map((c, i) => (
            <li key={i}>
              {c[0].toFixed(6)}, {c[1].toFixed(6)}
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
