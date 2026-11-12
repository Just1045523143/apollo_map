"""Signal geometry in the unchanged OpenDRIVE inertial frame (metres)."""
import math
from imap.lib.common import Point3d


def interpolate(points, s):
    points = sorted(points, key=lambda p: p.s)
    if not points or s < points[0].s - 1e-7 or s > points[-1].s + 1e-7:
        raise ValueError(f's={s} outside sampled geometry')
    for a, b in zip(points, points[1:]):
        if a.s <= s <= b.s and b.s > a.s:
            t = (s-a.s)/(b.s-a.s)
            p = Point3d(*(getattr(a, k)+(getattr(b, k)-getattr(a, k))*t for k in ('x', 'y', 'z')), s)
            delta = math.atan2(math.sin(b.yaw-a.yaw), math.cos(b.yaw-a.yaw))
            p.set_rotate(a.yaw + t*delta)
            return p
    import copy
    return copy.deepcopy(min(points, key=lambda p: abs(p.s-s)))


def road_point(road, s, t=0, z=0):
    p = interpolate(road.signal_reference_line, s)
    p.x -= math.sin(p.yaw)*t
    p.y += math.cos(p.yaw)*t
    p.z += z
    return p


def lane_s_at(lane, s):
    """Distance along the actual centre polyline in its travel direction."""
    target = interpolate(lane.center_line, s)
    traveled = 0.0
    increasing = int(lane.lane_id) < 0
    for a, b in zip(lane.center_line, lane.center_line[1:]):
        if min(a.s, b.s)-1e-8 <= s <= max(a.s, b.s)+1e-8:
            return traveled + math.dist((a.x,a.y,a.z), (target.x,target.y,target.z))
        traveled += math.dist((a.x,a.y,a.z), (b.x,b.y,b.z))
    return 0.0 if (s < lane.center_line[0].s) == increasing else lane.length


def rotate(u, v, w, yaw, pitch=0, roll=0):
    # Rz(yaw) Ry(pitch) Rx(roll): signal orientation in inertial axes.
    v, w = v*math.cos(roll)-w*math.sin(roll), v*math.sin(roll)+w*math.cos(roll)
    u, w = u*math.cos(pitch)+w*math.sin(pitch), -u*math.sin(pitch)+w*math.cos(pitch)
    return u*math.cos(yaw)-v*math.sin(yaw), u*math.sin(yaw)+v*math.cos(yaw), w


def lane_ids(section, signal):
    ranges = getattr(signal, 'validities', [])
    for lane in section.left + section.right:
        n = int(lane.lane_id)
        if lane.lane_type != 'driving' or n == 0:
            continue
        if signal.orientation == '+' and n > 0 or signal.orientation == '-' and n < 0:
            continue
        if ranges and not any(lo <= n <= hi for lo, hi in ranges):
            continue
        yield lane
