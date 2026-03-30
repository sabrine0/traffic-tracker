import { describe, it, expect } from "vitest";
import { validatePolygon } from "../../utils/validation";
import type { LatLngTuple } from "leaflet";

const VALID_SQUARE: LatLngTuple[] = [
  [40.75, -73.99],
  [40.75, -73.98],
  [40.76, -73.98],
  [40.76, -73.99],
];

describe("validatePolygon", () => {
  it("returns valid for a normal polygon", () => {
    const result = validatePolygon(VALID_SQUARE);
    expect(result.valid).toBe(true);
    expect(result.error).toBeNull();
  });

  it("rejects null", () => {
    const result = validatePolygon(null);
    expect(result.valid).toBe(false);
    expect(result.error).toContain("No area selected");
  });

  it("rejects empty array", () => {
    const result = validatePolygon([]);
    expect(result.valid).toBe(false);
    expect(result.error).toContain("No area selected");
  });

  it("rejects fewer than 3 vertices", () => {
    const result = validatePolygon([[0, 0], [1, 1]]);
    expect(result.valid).toBe(false);
    expect(result.error).toContain("at least 3");
  });

  it("rejects NaN coordinates", () => {
    const result = validatePolygon([[NaN, 0], [0, 0], [1, 1]]);
    expect(result.valid).toBe(false);
    expect(result.error).toContain("Invalid coordinate");
  });

  it("rejects Infinity coordinates", () => {
    const result = validatePolygon([[Infinity, 0], [0, 0], [1, 1]]);
    expect(result.valid).toBe(false);
    expect(result.error).toContain("Invalid coordinate");
  });

  it("rejects latitude out of range", () => {
    const result = validatePolygon([[91, 0], [0, 0], [1, 1]]);
    expect(result.valid).toBe(false);
    expect(result.error).toContain("Latitude out of range");
  });

  it("rejects longitude out of range", () => {
    const result = validatePolygon([[0, 181], [0, 0], [1, 1]]);
    expect(result.valid).toBe(false);
    expect(result.error).toContain("Longitude out of range");
  });

  it("rejects area exceeding 25 km² limit", () => {
    // Large polygon (~1° x 1° ≈ ~12,000 km² at mid-latitudes)
    const large: LatLngTuple[] = [
      [40, -74],
      [40, -73],
      [41, -73],
      [41, -74],
    ];
    const result = validatePolygon(large);
    expect(result.valid).toBe(false);
    expect(result.error).toContain("25 km²");
  });

  it("reports correct vertex index for bad coordinate", () => {
    const result = validatePolygon([[0, 0], [0, 1], [NaN, 1]]);
    expect(result.valid).toBe(false);
    expect(result.error).toContain("vertex 3");
  });
});
