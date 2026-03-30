import axios, { type CancelTokenSource } from "axios";

const API_BASE = import.meta.env.VITE_MAP2CAD_API_BASE || "/map2cad-api";

const api = axios.create({
  baseURL: API_BASE,
  timeout: 120000,
  headers: { "Content-Type": "application/json" },
});

export interface ExportRequest {
  polygon: [number, number][];
  options?: Record<string, boolean | string>;
}

export interface ExportStats {
  roads_found: number;
  roads_processed: number;
  intersections_detected: number;
  layers_generated: string[];
  entities_total: number;
  format: "dxf";
  time_seconds: number;
}

export interface ExportResponse {
  status: "success";
  download_url: string;
  filename: string;
  stats: ExportStats;
  warnings: string[];
}

export interface ExportError {
  status: "error";
  code: string;
  message: string;
}

const ERROR_MESSAGES: Record<string, string> = {
  AREA_TOO_LARGE: "Selected area is too large. Please select a smaller region.",
  NO_ROADS_FOUND: "No roads found in the selected area.",
  OVERPASS_ERROR: "OpenStreetMap server is slow. Please try again.",
  OVERPASS_TIMEOUT: "OpenStreetMap server timed out. Please try again.",
  OVERPASS_RATE_LIMITED: "OpenStreetMap rate limited. Please wait and try again.",
  OVERPASS_UNAVAILABLE: "OpenStreetMap server unavailable. Please try again later.",
  EXPORT_FAILED: "Export failed. Please try again.",
  CONVERSION_FAILED: "File conversion failed.",
  VALIDATION_ERROR: "Invalid selection. Please draw a valid area.",
  PAYLOAD_TOO_LARGE: "Request is too large. Please select a smaller area.",
};

export function getErrorMessage(code: string, fallback?: string): string {
  return ERROR_MESSAGES[code] || fallback || "An unexpected error occurred.";
}

export function createCancelToken(): CancelTokenSource {
  return axios.CancelToken.source();
}

export function isCancel(err: unknown): boolean {
  return axios.isCancel(err);
}

export async function exportArea(
  polygon: [number, number][],
  options?: Record<string, boolean | string>,
  cancelToken?: CancelTokenSource,
): Promise<ExportResponse> {
  const maxRetries = 1;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const { data } = await api.post<ExportResponse>(
        "/api/export",
        { polygon, options },
        { cancelToken: cancelToken?.token },
      );
      return data;
    } catch (err) {
      if (axios.isCancel(err)) throw err;

      // Only retry on network errors or 5xx, not on 4xx
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      const isRetryable = !status || status >= 500;

      if (attempt < maxRetries && isRetryable) {
        continue;
      }
      throw err;
    }
  }

  throw new Error("Export failed after retries");
}

export function getDownloadUrl(downloadUrl: string): string {
  if (/^https?:\/\//.test(downloadUrl)) {
    return downloadUrl;
  }
  if (downloadUrl.startsWith("/")) {
    return downloadUrl;
  }
  return downloadUrl;
}
