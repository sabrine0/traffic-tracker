import { describe, it, expect } from "vitest";
import { getErrorMessage } from "../../services/api";

describe("getErrorMessage", () => {
  it("returns mapped message for known error code", () => {
    expect(getErrorMessage("AREA_TOO_LARGE")).toContain("too large");
  });

  it("returns mapped message for overpass timeout", () => {
    expect(getErrorMessage("OVERPASS_TIMEOUT")).toContain("timed out");
  });

  it("returns fallback for unknown code", () => {
    expect(getErrorMessage("UNKNOWN_CODE", "Custom fallback")).toBe("Custom fallback");
  });

  it("returns generic message when no fallback provided", () => {
    expect(getErrorMessage("TOTALLY_UNKNOWN")).toContain("unexpected error");
  });

  it("maps all documented error codes", () => {
    const codes = [
      "AREA_TOO_LARGE",
      "NO_ROADS_FOUND",
      "OVERPASS_ERROR",
      "OVERPASS_TIMEOUT",
      "OVERPASS_RATE_LIMITED",
      "OVERPASS_UNAVAILABLE",
      "EXPORT_FAILED",
      "CONVERSION_FAILED",
      "VALIDATION_ERROR",
      "PAYLOAD_TOO_LARGE",
    ];
    for (const code of codes) {
      const msg = getErrorMessage(code);
      expect(msg).not.toContain("unexpected error");
    }
  });
});
