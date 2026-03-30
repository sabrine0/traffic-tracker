import SearchBar from "./SearchBar";
import SelectionInfo from "./SelectionInfo";
import ExportOptionsPanel from "./ExportOptions";
import { useSelection } from "../context/SelectionContext";
import { geodesicArea, isAreaTooLarge } from "../utils/geometry";
import type { ExportState } from "../hooks/useExport";

interface ControlPanelProps {
  open: boolean;
  onExport: () => void;
  exportState: ExportState;
}

export default function ControlPanel({ open, onExport, exportState }: ControlPanelProps) {
  const { coords } = useSelection();
  const hasSelection = coords !== null;
  const tooLarge = hasSelection && isAreaTooLarge(geodesicArea(coords));
  const canExport = hasSelection && !tooLarge && exportState !== "exporting";

  return (
    <aside
      aria-label="Control panel"
      className={`${
        open ? "translate-x-0" : "-translate-x-full"
      } fixed top-12 left-0 z-40 h-[calc(100%-3rem)] w-80 overflow-y-auto border-r border-gray-200 bg-white p-4 transition-transform duration-200 md:static md:translate-x-0`}
    >
      <Section title="Search">
        <SearchBar />
      </Section>

      <Section title="Selection Tools">
        <p className="text-sm text-gray-400">
          Use the draw tools on the map to select an area.
        </p>
        <p className="mt-1 text-xs text-gray-300">
          Press <kbd className="rounded bg-gray-100 px-1 py-0.5 text-gray-500">Esc</kbd> to clear selection
        </p>
      </Section>

      <Section title="Area Info">
        <SelectionInfo />
        {tooLarge && (
          <p className="mt-1 text-xs text-red-500">Area exceeds the 10 km² limit</p>
        )}
      </Section>

      <Section title="Export Options">
        <ExportOptionsPanel />
      </Section>

      <Section title="Export">
        <button
          disabled={!canExport}
          onClick={onExport}
          aria-label={exportState === "exporting" ? "Export in progress" : "Export selected area as DXF file"}
          title={!hasSelection ? "Draw an area on the map first" : tooLarge ? "Area is too large" : "Export selected area as DXF"}
          className={`w-full rounded px-4 py-2.5 text-sm font-medium min-h-[44px] ${
            canExport
              ? "bg-blue-600 text-white hover:bg-blue-700 cursor-pointer"
              : "bg-gray-300 text-gray-500 cursor-not-allowed"
          }`}
        >
          {exportState === "exporting" ? "Exporting..." : "Export DXF"}
        </button>
        {!hasSelection && (
          <p className="mt-1.5 text-xs text-gray-400">
            Select an area on the map to enable export. Press <kbd className="rounded bg-gray-100 px-1 py-0.5 text-gray-500">Enter</kbd> as shortcut.
          </p>
        )}
      </Section>
    </aside>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">{title}</h3>
      {children}
    </div>
  );
}
