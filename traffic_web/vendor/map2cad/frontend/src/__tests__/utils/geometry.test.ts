import { describe, it, expect } from "vitest";
import { geodesicArea, formatArea, isAreaTooLarge, MAX_AREA_M2 } from "../../utils/geometry";
import type { LatLngTuple } from "leaflet";

describe("geodesicArea", () => {
  it("returns 0 for fewer than 3 points", () => {
    expect(geodesicArea([])).toBe(0);
    expect(geodesicArea([[0, 0]])).toBe(0);
    expect(geodesicArea([[0, 0], [1, 1]])).toBe(0);
  });

  it("calculates area for a known square (~1km x 1km near equator)", () => {
    // ~1km square at equator: 0.009 degrees ≈ 1km
    const coords: LatLngTuple[] = [
      [0, 0],
      [0, 0.009],
      [0.009, 0.009],
      [0.009, 0],
    ];
    const area = geodesicArea(coords);
    // Should be roughly 1 km² = 1,000,000 m²
    expect(area).toBeGreaterThan(500_000);
    expect(area).toBeLessThan(2_000_000);
  });

  it("larger polygon gives larger area", () => {
    const small: LatLngTuple[] = [[40, -74], [40, -73.99], [40.01, -73.99], [40.01, -74]];
    const large: LatLngTuple[] = [[40, -74], [40, -73.9], [40.1, -73.9], [40.1, -74]];
    expect(geodesicArea(large)).toBeGreaterThan(geodesicArea(small));
  });
});

describe("formatArea", () => {
  it("formats small areas in m²", () => {
    expect(formatArea(500)).toContain("m\u00B2");
    expect(formatArea(999_999)).toContain("m\u00B2");
  });

  it("formats large areas in km²", () => {
    expect(formatArea(1_000_000)).toContain("km\u00B2");
    expect(formatArea(5_000_000)).toContain("km\u00B2");
  });
});

describe("isAreaTooLarge", () => {
  it("returns false for small areas", () => {
    expect(isAreaTooLarge(1_000_000)).toBe(false);
  });

  it("returns true for areas exceeding limit", () => {
    expect(isAreaTooLarge(MAX_AREA_M2 + 1)).toBe(true);
  });

  it("returns false for area exactly at limit", () => {
    expect(isAreaTooLarge(MAX_AREA_M2)).toBe(false);
  });
});
