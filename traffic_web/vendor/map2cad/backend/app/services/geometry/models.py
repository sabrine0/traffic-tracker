"""Data models for geometry processing pipeline."""

from dataclasses import dataclass
from shapely.geometry import LineString


@dataclass
class RoadSegment:
    """A single road segment with UTM-projected centerline and all attributes."""

    centerline: LineString
    name: str = ""
    highway_type: str = "residential"
    classification: str = "local"
    width_m: float = 6.0
    lanes: int = 2
    lane_width_m: float = 3.0
    oneway: bool = False
    sidewalk: str = "both"  # both, left, right, no
    has_median: bool = False
    median_width_m: float = 2.0

    def __repr__(self) -> str:
        return f"RoadSegment(name={self.name!r}, type={self.highway_type}, width={self.width_m}m, len={self.centerline.length:.1f}m)"
