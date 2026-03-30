import type { ExportStats } from "../services/api";

export type ExportStatus = "idle" | "exporting" | "success" | "error";

interface ExportPanelProps {
  status: ExportStatus;
  errorMessage?: string | null;
  stats?: ExportStats | null;
  warnings?: string[];
  downloadUrl?: string | null;
  onRetry?: () => void;
}

export default function ExportPanel({
  status,
  errorMessage,
  stats,
  warnings,
  downloadUrl,
  onRetry,
}: ExportPanelProps) {
  if (status === "idle") return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-gray-200 bg-white px-4 py-3 shadow-lg md:left-80">
      {status === "exporting" && (
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
            <span className="text-sm text-gray-600">
              Generating CAD file...
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-200">
            <div className="h-full animate-pulse rounded-full bg-blue-500" style={{ width: "60%", animation: "progress-indeterminate 2s ease-in-out infinite" }} />
          </div>
        </div>
      )}

      {status === "success" && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-green-600">
              Export complete!
            </span>
            {downloadUrl && (
              <a
                href={downloadUrl}
                className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
                download
              >
                Download DXF
              </a>
            )}
          </div>
          {stats && (
            <div className="flex gap-4 text-xs text-gray-500">
              <span>{stats.roads_processed} roads</span>
              <span>{stats.intersections_detected} intersections</span>
              <span>{stats.entities_total} entities</span>
              <span>{stats.time_seconds}s</span>
            </div>
          )}
          {warnings && warnings.length > 0 && (
            <div className="text-xs text-amber-600">
              {warnings.length} warning{warnings.length > 1 ? "s" : ""}:{" "}
              {warnings[0]}
              {warnings.length > 1 && ` (+${warnings.length - 1} more)`}
            </div>
          )}
        </div>
      )}

      {status === "error" && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-red-600">
            {errorMessage || "Export failed. Please try again."}
          </span>
          {onRetry && (
            <button
              onClick={onRetry}
              className="rounded bg-red-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-700"
            >
              Retry
            </button>
          )}
        </div>
      )}
    </div>
  );
}
