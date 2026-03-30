import { useState, useCallback, useEffect, useRef } from "react";
import Navbar from "./Navbar";
import ControlPanel from "./ControlPanel";
import MapView from "./MapView";
import ExportPanel from "./ExportPanel";
import ToastContainer from "./ui/Toast";
import { useExport } from "../hooks/useExport";
import { useExportOptions } from "../context/ExportContext";
import { useSelection } from "../context/SelectionContext";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";
import { useToast } from "../hooks/useToast";

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { state, stats, warnings, downloadUrl, errorMessage, startExport, reset } = useExport();
  const { options } = useExportOptions();
  const { coords, clearSelection } = useSelection();
  const { toasts, addToast, dismiss } = useToast();
  const prevStateRef = useRef(state);

  useEffect(() => {
    if (prevStateRef.current === "exporting" && state === "success") {
      addToast("success", "Export complete! Your file is ready to download.");
    } else if (prevStateRef.current === "exporting" && state === "error") {
      addToast("error", errorMessage || "Export failed.");
    }
    prevStateRef.current = state;
  }, [state, addToast, errorMessage]);

  const handleExportShortcut = useCallback(() => {
    if (coords && state !== "exporting") {
      startExport({ ...options });
    }
  }, [coords, state, startExport, options]);

  const handleEscape = useCallback(() => {
    if (state === "success" || state === "error") {
      reset();
    } else {
      clearSelection();
    }
  }, [state, reset, clearSelection]);

  const handleFocusSearch = useCallback(() => {
    const input = document.querySelector<HTMLInputElement>('input[placeholder="Search location..."]');
    input?.focus();
  }, []);

  useKeyboardShortcuts({
    onEscape: handleEscape,
    onExport: handleExportShortcut,
    onFocusSearch: handleFocusSearch,
  });

  return (
    <div className="flex h-full flex-col">
      <Navbar onToggleSidebar={() => setSidebarOpen((o) => !o)} sidebarOpen={sidebarOpen} />

      <div className="flex flex-1 pt-12">
        <ControlPanel
          open={sidebarOpen}
          onExport={() => startExport({ ...options })}
          exportState={state}
        />

        <main className="relative flex-1">
          <MapView />
        </main>
      </div>

      <ExportPanel
        status={state}
        stats={stats}
        warnings={warnings}
        downloadUrl={downloadUrl}
        errorMessage={errorMessage}
        onRetry={() => startExport({ ...options })}
      />

      <ToastContainer toasts={toasts} onDismiss={dismiss} />

      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/30 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
    </div>
  );
}
