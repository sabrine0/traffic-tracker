from app.services.osm_parser import parse_ways, RoadSegment


def _make_way(way_id: int, tags: dict, node_count: int = 3) -> dict:
    nodes = [{"lat": 40.75 + i * 0.001, "lon": -73.99} for i in range(node_count)]
    return {"id": way_id, "nodes": nodes, "tags": tags}


def test_residential_defaults():
    ways = [_make_way(1, {"highway": "residential"})]
    segments = parse_ways(ways)
    assert len(segments) == 1
    seg = segments[0]
    assert seg.highway_type == "residential"
    assert seg.classification == "local"
    assert seg.width_m == 6.0
    assert seg.lanes == 2
    assert seg.sidewalk == "both"
    assert seg.oneway is False
    assert seg.has_median is False


def test_primary_with_lanes():
    ways = [_make_way(2, {"highway": "primary", "lanes": "4", "name": "Main St"})]
    segments = parse_ways(ways)
    seg = segments[0]
    assert seg.lanes == 4
    assert seg.width_m == 13.0  # 4 * 3.25
    assert seg.name == "Main St"


def test_width_override():
    ways = [_make_way(3, {"highway": "residential", "width": "8"})]
    segments = parse_ways(ways)
    assert segments[0].width_m == 8.0


def test_width_with_unit():
    ways = [_make_way(4, {"highway": "residential", "width": "7.5 m"})]
    segments = parse_ways(ways)
    assert segments[0].width_m == 7.5


def test_oneway():
    ways = [_make_way(5, {"highway": "residential", "oneway": "yes"})]
    segments = parse_ways(ways)
    assert segments[0].oneway is True


def test_sidewalk_left():
    ways = [_make_way(6, {"highway": "residential", "sidewalk": "left"})]
    segments = parse_ways(ways)
    assert segments[0].sidewalk == "left"


def test_motorway_is_divided():
    ways = [_make_way(7, {"highway": "motorway"})]
    segments = parse_ways(ways)
    seg = segments[0]
    assert seg.has_median is True
    assert seg.classification == "main"
    assert seg.lanes == 3
    assert seg.width_m == 10.5
    assert seg.sidewalk == "no"


def test_unknown_highway_defaults():
    ways = [_make_way(8, {"highway": "cycleway"})]
    segments = parse_ways(ways)
    seg = segments[0]
    assert seg.classification == "local"
    assert seg.width_m == 6.0


def test_service_road():
    ways = [_make_way(9, {"highway": "service"})]
    segments = parse_ways(ways)
    seg = segments[0]
    assert seg.width_m == 3.0
    assert seg.lanes == 1
    assert seg.sidewalk == "no"


def test_link_road_strips_suffix():
    ways = [_make_way(10, {"highway": "primary_link"})]
    segments = parse_ways(ways)
    assert segments[0].highway_type == "primary"


def test_skips_single_node_ways():
    ways = [_make_way(11, {"highway": "residential"}, node_count=1)]
    segments = parse_ways(ways)
    assert len(segments) == 0


def test_oneway_reverse():
    """oneway=-1 reverses node order."""
    ways = [_make_way(12, {"highway": "residential", "oneway": "-1"}, node_count=3)]
    segments = parse_ways(ways)
    seg = segments[0]
    assert seg.oneway is True
    # Nodes should be reversed: last original node is first
    assert seg.nodes[0]["lat"] > seg.nodes[-1]["lat"]
