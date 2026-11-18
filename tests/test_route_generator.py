"""Loop routes from a start point (src/route_generator.py), with a fake router: no internet needed."""

import math

from src import route_generator as rg

START = (-6.186, 106.887)


def straight_router(points):
    """A fake router: straight lines between the points, 1.3x longer like real streets."""
    km = sum(rg.distance_km(a, b) for a, b in zip(points, points[1:]))
    return km * 1.3, list(points)


def test_waypoints_sit_on_a_circle_through_the_start():
    points = rg.loop_points(START, 1.0, 90)
    assert points[0] == points[-1] == START and len(points) == rg.WAYPOINTS + 2
    centre = rg.destination(*START, 90, 1.0)
    for point in points:
        assert abs(rg.distance_km(centre, point) - 1.0) < 1e-6


def test_loop_is_scaled_to_the_target_distance():
    result = rg.loop(START, 5.0, 0, router=straight_router)
    assert abs(result["km"] - 5.0) <= rg.TOLERANCE * 5.0
    assert result["path"][0] == START


def test_directions_with_no_streets_are_replaced_by_the_ones_between():
    def no_south(points):
        if any(lat < START[0] - 0.003 for lat, _ in points):      # "the sea" to the south
            raise ValueError("no route")
        return straight_router(points)

    loops = rg.generate(START, 5.0, options=3, router=no_south)
    bearings = [round(l["bearing"]) for l in loops]
    assert len(set(bearings)) == len(loops) >= 1
    assert 120 not in bearings and 240 not in bearings                # those circles reach south
    assert any(b not in (0, 120, 240) for b in bearings)               # an in-between direction filled in


def test_a_loop_far_from_the_target_is_not_offered():
    stuck = lambda points: (1.0, list(points))                        # streets never give more than 1 km
    assert rg.generate(START, 5.0, router=stuck) == []


def test_repeated_share_finds_out_and_back():
    a, b, c = START, rg.destination(*START, 0, 0.5), rg.destination(*START, 90, 0.5)
    assert rg.repeated_share([a, b, c, a]) == 0
    assert math.isclose(rg.repeated_share([a, b, a]), 0.5)        # the way back is the same street


def test_gpx_has_every_point_and_a_safe_name():
    gpx = rg.to_gpx([START, (-6.19, 106.89)], "5 km <loop> & back")
    assert gpx.count("<trkpt") == 2 and "<name>5 km loop and back</name>" in gpx


def walk(*moves, start=START):
    """A path from start: each move is (compass heading, metres), with a point every 10 m."""
    path = [start]
    for bearing, metres in moves:
        for _ in range(int(metres // 10)):
            path.append(rg.destination(*path[-1], bearing, 0.01))
    return path


def test_dead_end_detours_are_cut():
    out = walk((0, 100))
    spur = walk((90, 50), start=out[-1])
    back = list(reversed(spur))[1:]
    path = out + spur[1:] + back + walk((0, 100), start=out[-1])[1:]
    trimmed = rg.trim_spurs(path)
    assert len(trimmed) == len(path) - 2 * (len(spur) - 1)
    assert all(not rg.same(p, spur[-1]) for p in trimmed)             # the dead end is gone
    assert rg.trim_spurs(out) == out                                  # nothing to cut


def test_turns_are_named_from_the_path_and_jogs_merge():
    path = walk((0, 200), (90, 10), (0, 200), (270, 200))   # north, a 10 m jog east, north, then west
    raw = [{"km": 0, "dir": "right", "street": "Jalan A", "lat": path[20][0], "lon": path[20][1]},
           {"km": 0, "dir": "left", "street": "Jalan B", "lat": path[21][0], "lon": path[21][1]},
           {"km": 0, "dir": "left", "street": "Jalan C", "lat": path[41][0], "lon": path[41][1]}]
    turns = rg.clean_turns(path, raw)
    assert [t["dir"] for t in turns] == ["left", "finish"]           # the jog is going straight on
    assert turns[0]["street"] == "Jalan C" and abs(turns[0]["km"] - 0.41) < 0.01


def test_google_maps_link_follows_the_loop():
    result = rg.loop(START, 5.0, 0, router=straight_router)
    assert len(result["via"]) == rg.WAYPOINTS
    assert all(any(rg.same(v, p) for p in result["path"]) for v in result["via"])   # points on the loop itself
    url = rg.google_maps_url(START, result["via"])
    assert url.startswith("https://www.google.com/maps/dir/?api=1&")
    assert "travelmode=walking" in url and url.count("%7C") == rg.WAYPOINTS - 1     # waypoints joined by |
    assert "origin=-6.186000%2C106.887000" in url and "destination=-6.186000%2C106.887000" in url
