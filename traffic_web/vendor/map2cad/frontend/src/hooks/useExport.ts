import { useState, useCallback, useRef, useEffect } from "react";
import {
  exportArea,
  getErrorMessage,
  getDownloadUrl,
  createCancelToken,
  isCancel,
  type ExportStats,
} from "../services/api";
import { useSelection } from "../context/SelectionContext";
import { validatePolygon } from "../utils/validation";
import type { LatLngTuple } from "leaflet";
import type { CancelTokenSource } from "axios";

export type ExportState = "idle" | "exporting" | "success" | "error";

interface ExportResult {
  state: ExportState;
  stats: ExportStats | null;
  warnings: string[];
  downloadUrl: string | null;
  errorMessage: string | null;
  errorCode: string | null;
  startExport: (options?: Record<string, boolean | string>) => void;
  reset: () => void;
}

export function useExport(): ExportResult {
  const { coords } = useSelection();
  const [state, setState] = useState<ExportState>("idle");
  const [stats, setStats] = useState<ExportStats | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const cancelRef = useRef<CancelTokenSource | null>(null);

  // Cancel in-flight request on unmount
  useEffect(() => {
    return () => {
      cancelRef.current?.cancel("Component unmounted");
    };
  }, []);

  const startExport = useCallback(
    async (options?: Record<string, boolean | string>) => {
      if (!coords) return;

      // Frontend validation before sending request
      const validation = validatePolygon(coords);
      if (!validation.valid) {
        setState("error");
        setErrorCode("VALIDATION_ERROR");
        setErrorMessage(validation.error);
        return;
      }

      // Cancel any previous in-flight request
      cancelRef.current?.cancel("New export started");

      setState("exporting");
      setErrorMessage(null);
      setErrorCode(null);
      setStats(null);
      setWarnings([]);
      setDownloadUrl(null);

      const cancelToken = createCancelToken();
      cancelRef.current = cancelToken;

      try {
        const polygon = coords.map(
          (c: LatLngTuple) => [c[1], c[0]] as [number, number]
        );

        const result = await exportArea(polygon, options, cancelToken);

        setState("success");
        setStats(result.stats);
        setWarnings(result.warnings);
        setDownloadUrl(getDownloadUrl(result.download_url));
      } catch (err: unknown) {
        // Don't update state if request was cancelled
        if (isCancel(err)) return;

        setState("error");
        if (
          err &&
          typeof err === "object" &&
          "response" in err &&
          (err as { response?: { data?: { code?: string; message?: string } } })
            .response?.data
        ) {
          const data = (
            err as { response: { data: { code: string; message: string } } }
          ).response.data;
          setErrorCode(data.code);
          setErrorMessage(getErrorMessage(data.code, data.message));
        } else if (
          err &&
          typeof err === "object" &&
          "code" in err &&
          (err as { code?: string }).code === "ECONNABORTED"
        ) {
          setErrorCode("TIMEOUT");
          setErrorMessage("Request timed out. The server may be busy — please try again.");
        } else {
          setErrorCode("NETWORK_ERROR");
          setErrorMessage(
            "Network error. Check your connection and try again."
          );
        }
      } finally {
        cancelRef.current = null;
      }
    },
    [coords]
  );

  const reset = useCallback(() => {
    cancelRef.current?.cancel("Reset");
    cancelRef.current = null;
    setState("idle");
    setStats(null);
    setWarnings([]);
    setDownloadUrl(null);
    setErrorMessage(null);
    setErrorCode(null);
  }, []);

  return {
    state,
    stats,
    warnings,
    downloadUrl,
    errorMessage,
    errorCode,
    startExport,
    reset,
  };
}
