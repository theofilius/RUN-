"""Loop routes of a chosen distance from a start point, on real streets.

How a loop is made:
  1. Draw a circle that passes through the start, its centre in one compass direction.
  2. Put WAYPOINTS points on the circle, evenly spaced, and ask a walking router
     (OSRM on OpenStreetMap, routing.openstreetmap.de: free, no key) for the path
     start -> points -> start.
  3. Streets are not a circle, so the first loop is too long or too short. Search the
     radius: scale by target / actual until there is one radius too short and one too
     long, then halve the gap (bisection), up to MAX_TRIES router calls. Bisection matters:
     a waypoint can snap across a canal or toll road, so the length jumps (0.18 km radius
     gave 6.1 km, 0.09 km gave 0.65 km) and plain scaling overshoots back and forth.
  4. A loop more than MAX_OFF from the target is dropped; if that leaves fewer than
     OPTIONS loops, the directions in between are tried too.
Different directions give different loops; the runner picks one and can download it
as GPX to load on a Garmin watch as a course (Garmin Connect: Training -> Courses -> Import).

Every number here is an own rule (route shape, not training load), set by trying it on
Jakarta streets: none of them changes how far or how hard the plan asks you to run.
"""

import json
import math
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROUTER = "https://routing.openstreetmap.de/routed-foot/route/v1/foot/"
USER_AGENT = "running-training-analyzer (personal training dashboard)"
EARTH_KM = 6371.0
WAYPOINTS = 3            # points on the circle besides the start: fewer gives out-and-backs, more zig-zags,
                         # and 3 is also the most a Google Maps link takes when it opens in a phone browser
ROAD_FACTOR = 1.3        # own rule: a street loop is about 1.3x the circle it follows (first guess only)
TOLERANCE = 0.05         # own rule: a loop within 5% of the target is close enough
MAX_TRIES = 6            # own rule: router calls per direction before taking the closest loop
MAX_OFF = 0.15           # own rule: a loop more than 15% off the target is not offered
OPTIONS = 3
TIMEOUT_S = 20
MERGE_KM = 0.03          # own rule: turns closer than 30 m are one move (a jog across a divided road)
HEADING_KM = 0.02        # own rule: the direction at a turn is read over 20 m before and after it


def destination(lat, lon, bearing_deg, km):
    """The point km away from lat, lon in compass direction bearing_deg (great circle)."""
    d, b = km / EARTH_KM, math.radians(bearing_deg)
    lat1, lon1 = math.radians(lat), math.radians(lon)
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(b))
    lon2 = lon1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(lat1), math.cos(d) - math.sin(lat1) * math.sin(lat2))
    return math.degrees(lat2), math.degrees(lon2)


def distance_km(a, b):
    """Great-circle distance between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(h))


def loop_points(start, radius_km, bearing_deg, n=WAYPOINTS):
    """start, then n points on a circle through start whose centre lies at bearing_deg, then start."""
    centre = destination(*start, bearing_deg, radius_km)
    back = (bearing_deg + 180) % 360          # from the centre, the start is in this direction
    ring = [destination(*centre, back + 360 * (i + 1) / (n + 1), radius_km) for i in range(n)]
    return [start, *ring, start]


def ask_router(points):
    """(km, [(lat, lon), ...], turns) of the walking route through points, in order."""
    path = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    url = f"{ROUTER}{quote(path, safe=',;.-')}?overview=full&geometries=geojson&steps=true"
    with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=TIMEOUT_S) as response:
        answer = json.load(response)
    if answer.get("code") != "Ok" or not answer.get("routes"):
        raise ValueError(answer.get("message") or answer.get("code") or "no route")
    route = answer["routes"][0]
    return (route["distance"] / 1000, [(lat, lon) for lon, lat in route["geometry"]["coordinates"]],
            turns(route["legs"]))


def turns(legs):
    """Every place the router says the way changes, with the street taken there:
    [{"km", "dir", "street", "lat", "lon"}]. Raw: clean_turns names and filters them
    from the path itself, after the detours are cut."""
    out, km = [], 0.0
    for leg in legs:
        for step in leg["steps"]:
            maneuver = step["maneuver"]
            lon, lat = maneuver["location"]
            if maneuver["type"] not in ("arrive",) and not (maneuver["type"] == "depart" and not out and km == 0):
                out.append({"km": km, "dir": maneuver.get("modifier") or maneuver["type"],
                            "street": step.get("name") or "", "lat": lat, "lon": lon})
            km += step["distance"] / 1000
    return out


def repeated_share(path):
    """Share of the distance run on a street already used in this loop (0 = a clean loop).

    Points are rounded to about 10 m, so the same street run twice (either way) matches.
    """
    seen, total, repeated = set(), 0.0, 0.0
    for a, b in zip(path, path[1:]):
        step = distance_km(a, b)
        key = frozenset({(round(a[0], 4), round(a[1], 4)), (round(b[0], 4), round(b[1], 4))})
        if len(key) < 2:
            continue
        total += step
        if key in seen:
            repeated += step
        seen.add(key)
    return repeated / total if total else 0.0


def same(a, b):
    """The same point (to about 10 cm): the router repeats exact node coordinates on the way back."""
    return round(a[0], 6) == round(b[0], 6) and round(a[1], 6) == round(b[1], 6)


def path_km(path):
    return sum(distance_km(a, b) for a, b in zip(path, path[1:]))


def trim_spurs(path):
    """The path without dead-end detours: ... A, B, C, B, A ... becomes ... A ...

    A waypoint on the circle can snap onto a side street, so the router goes in and comes
    straight back out the same way. Nobody wants to run that, and it is not part of the loop.
    """
    path = list(path)
    i = 1
    while i < len(path) - 1:
        if same(path[i - 1], path[i + 1]):
            k = 1
            while i - k - 1 >= 0 and i + k + 1 < len(path) and same(path[i - k - 1], path[i + k + 1]):
                k += 1
            del path[i - k + 1:i + k + 1]          # keep path[i - k], which equals path[i + k]
            i = max(1, i - k)
        else:
            i += 1
    return path


def heading(a, b):
    """Compass heading from a to b, in degrees."""
    lat1, lat2, dlon = math.radians(a[0]), math.radians(b[0]), math.radians(b[1] - a[1])
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.degrees(math.atan2(y, x)) % 360


def turn_name(before, after):
    """left / right / slight left / slight right / uturn / straight from the headings around a turn."""
    angle = (after - before) % 360
    if angle < 30 or angle > 330:
        return "straight"
    if 150 <= angle <= 210:
        return "uturn"
    side = "right" if angle < 180 else "left"
    return f"slight {side}" if angle < 60 or angle > 300 else side


def clean_turns(path, raw):
    """The router's turns on the trimmed path, merged and named from the path's own shape.

    A turn whose point was cut with a detour is gone; turns closer than MERGE_KM become
    one (named after the last street); each is then left/right/... from the heading over
    HEADING_KM before and after it, so "left then right" across a road is "straight" and
    left out. The finish is added at the end.
    """
    along = [0.0]
    for a, b in zip(path, path[1:]):
        along.append(along[-1] + distance_km(a, b))
    found, start_at = [], 0
    for turn in raw:
        if turn["dir"] == "finish" or turn.get("lat") is None:
            continue
        at = next((i for i in range(start_at, len(path)) if same(path[i], (turn["lat"], turn["lon"]))), None)
        if at is not None:
            found.append((at, turn))
            start_at = at
    groups = []
    for at, turn in found:
        if groups and along[at] - along[groups[-1][-1][0]] < MERGE_KM:
            groups[-1].append((at, turn))
        else:
            groups.append([(at, turn)])

    def walk(i, step, km):   # the index about km away from i, going step (-1 back, +1 ahead)
        j = i
        while 0 <= j + step < len(path) and abs(along[j] - along[i]) < km:
            j += step
        return j

    out = []
    for group in groups:
        first, last = group[0][0], group[-1][0]
        before, after = walk(first, -1, HEADING_KM), walk(last, 1, HEADING_KM)
        if before == first or after == last:
            continue
        name = turn_name(heading(path[before], path[first]), heading(path[last], path[after]))
        if name != "straight":
            out.append({"km": along[first], "dir": name, "street": group[-1][1]["street"],
                        "lat": path[first][0], "lon": path[first][1]})
    out.append({"km": along[-1], "dir": "finish", "street": "", "lat": path[-1][0], "lon": path[-1][1]})
    return out


def loop(start, target_km, bearing_deg, router=ask_router):
    """The loop in one direction closest to target_km: {"bearing", "km", "path", "turns", "repeated"}."""
    radius = target_km / (2 * math.pi * ROAD_FACTOR)
    short, long = None, None          # the largest radius found too short, the smallest found too long
    best = None
    for _ in range(MAX_TRIES):
        points = loop_points(start, radius, bearing_deg)
        km, path, *more = router(points)
        trimmed = trim_spurs(path)
        km -= path_km(path) - path_km(trimmed)          # the detours are not run
        path = trimmed
        if best is None or abs(km - target_km) < abs(best["km"] - target_km):
            best = {"bearing": bearing_deg, "km": km, "path": path, "turns": more[0] if more else [],
                    "ring": points[1:-1]}
        if abs(km - target_km) <= TOLERANCE * target_km:
            break
        if km < target_km:
            short = radius if short is None else max(short, radius)
        else:
            long = radius if long is None else min(long, radius)
        if short is not None and long is not None:
            radius = (short + long) / 2
        else:
            radius *= min(max(target_km / km, 0.5), 2.0) if km > 0 else 2.0   # at most halve or double
    best["repeated"] = repeated_share(best["path"])
    best["turns"] = clean_turns(best["path"], best["turns"])
    best["via"] = via_points(best["path"], best.pop("ring"))
    return best


def via_points(path, ring):
    """For each circle point, in order, the nearest point of the loop itself.

    The loop is the shortest walk from one circle point to the next, so another router
    given these points (Google Maps) draws nearly the same loop. Taken from the loop, not
    the circle: a circle point can sit at the end of a detour that was cut.
    """
    via, start_at = [], 0
    for point in ring:
        if start_at >= len(path):
            break
        at = min(range(start_at, len(path)), key=lambda i: distance_km(path[i], point))
        via.append(path[at])
        start_at = at + 1
    return via


def google_maps_url(start, via):
    """A link that opens the loop in Google Maps as walking directions with voice guidance.

    Origin and destination are the start; via points are the waypoints (at most 3 work
    when the link opens in a phone browser). dir_action=navigate starts navigation at
    once when you are at the start, and shows the route preview otherwise.
    """
    place = lambda p: f"{p[0]:.6f},{p[1]:.6f}"
    return "https://www.google.com/maps/dir/?" + urlencode({
        "api": 1, "origin": place(start), "destination": place(start),
        "waypoints": "|".join(place(p) for p in via), "travelmode": "walking", "dir_action": "navigate"})


def generate(start, target_km, options=OPTIONS, first_bearing=0, router=ask_router):
    """Up to options loops from start, each within MAX_OFF of target_km.

    The circle centres are spread evenly around the compass (first_bearing turns them all);
    the directions in between are tried only when too few loops came close enough. A
    direction the router cannot route (sea, no streets) is skipped.
    """
    step = 360 / options
    bearings = [first_bearing + step * i for i in range(options)] + \
               [first_bearing + step * (i + 0.5) for i in range(options)]
    loops = []
    for bearing in bearings:
        if len(loops) == options:
            break
        try:
            found = loop(start, target_km, bearing % 360, router)
        except (OSError, ValueError):
            continue
        if abs(found["km"] - target_km) <= MAX_OFF * target_km:
            loops.append(found)
    return loops


def to_gpx(path, name):
    """A GPX track of the path, for Garmin Connect's course import or any running app."""
    safe = name.replace("&", "and").replace("<", "").replace(">", "")
    points = "".join(f'<trkpt lat="{lat:.6f}" lon="{lon:.6f}"/>' for lat, lon in path)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<gpx version="1.1" creator="Running Training Analyzer" xmlns="http://www.topografix.com/GPX/1/1">'
            f"<trk><name>{safe}</name><trkseg>{points}</trkseg></trk></gpx>\n")
