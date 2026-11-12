"""Traffic lights, explicit stop lines and lane overlaps in the source frame."""
import logging
import math

import imap.global_var as global_var
from imap.lib.signal_geometry import interpolate, lane_ids, road_point, rotate


def number(value, default=0):
    result = default if value is None else float(value)
    if not math.isfinite(result):
        raise ValueError('Signal/object geometry must be finite')
    return result


def section_at(road, s):
    if not 0 <= s <= road.length:
        raise ValueError(f'Signal s={s} outside road {road.road_id}')
    return max(i for i, section in enumerate(road.lanes.lane_sections) if section.s <= s)


def body(pb, road, signal):
    from imap.proto import map_signal_pb2
    origin = road_point(road, number(signal.s), number(signal.t), number(signal.zOffset))
    yaw = origin.yaw + (math.pi if signal.orientation == '+' else 0) + number(signal.hOffset)
    width, height = number(signal.width, 0.45), number(signal.height, 1.2)
    if width <= 0 or height <= 0:
        raise ValueError(f'Traffic light {signal.id} needs positive width and height')
    def position(target, v, w):
        x, y, z = rotate(0, v, w, yaw, number(signal.pitch), number(signal.roll))
        target.x, target.y, target.z = origin.x+x, origin.y+y, origin.z+z
    for v, w in [(-width/2, 0), (width/2, 0), (width/2, height), (-width/2, height)]:
        position(pb.boundary.point.add(), v, w)
    # OpenDRIVE 1000001/-1 is a generic traffic light: do not invent bulb layout.
    pb.type = map_signal_pb2.Signal.UNKNOWN
    bulb = pb.subsignal.add()
    bulb.id.id = pb.id.id + '_center'
    bulb.type = map_signal_pb2.Subsignal.UNKNOWN
    position(bulb.location, 0, height/2)


def stop_object(road, obj):
    """Return the centre line of a transverse roadMark/signalLines object."""
    s, t = number(obj.get('s')), number(obj.get('t'))
    origin = road_point(road, s, t, number(obj.get('zOffset')))
    local = obj.findall('.//cornerLocal')
    corners = obj.findall('.//cornerRoad')
    if corners:
        s = sum(number(p.get('s')) for p in corners)/len(corners)
        lo, hi = min(corners, key=lambda c: number(c.get('t'))), max(corners, key=lambda c: number(c.get('t')))
        return s, [road_point(road, s, number(p.get('t')), number(p.get('dz'))) for p in (lo, hi)]
    if local:
        u = (min(number(p.get('u')) for p in local)+max(number(p.get('u')) for p in local))/2
        vs = [number(p.get('v')) for p in local]
        zs = [number(p.get('z')) for p in local]
        z = sum(zs)/len(zs)
    else:
        u, z = 0, 0
        vs = [-number(obj.get('width'))/2, number(obj.get('width'))/2]
    if max(vs)-min(vs) <= 0:
        raise ValueError(f'Stop line {obj.get("id")} has no transverse extent')
    result = []
    for v in (min(vs), max(vs)):
        dx, dy, dz = rotate(u, v, z, origin.yaw+number(obj.get('hdg')),
                            number(obj.get('pitch')), number(obj.get('roll')))
        from imap.lib.common import Point3d
        result.append(Point3d(origin.x+dx, origin.y+dy, origin.z+dz, s))
    return s, result


def intersection_station(lane, ends):
    """Return actual lane-local arc length where the explicit line crosses it."""
    c, d = ends
    traveled = 0.0
    for a, b in zip(lane.center_line, lane.center_line[1:]):
        rx, ry, sx, sy = b.x-a.x, b.y-a.y, d.x-c.x, d.y-c.y
        denominator = rx*sy-ry*sx
        length = math.dist((a.x,a.y,a.z), (b.x,b.y,b.z))
        if abs(denominator) > 1e-10:
            t = ((c.x-a.x)*sy-(c.y-a.y)*sx)/denominator
            u = ((c.x-a.x)*ry-(c.y-a.y)*rx)/denominator
            if -1e-7 <= t <= 1+1e-7 and -1e-7 <= u <= 1+1e-7:
                return traveled+max(0, min(1, t))*length
        traveled += length
    return None


def is_stop(obj):
    return obj.get('type') == 'stopLine' or (obj.get('type') == 'roadMark' and obj.get('subtype') in ('signalLines', 'stopLine'))


def bound_stop_lines(road, signal):
    """Resolve every stop-line binding; never silently ignore a broken binding."""
    objects_by_id = {o.get('id'): o for o in road.objects}
    bound = []
    for ref in getattr(signal, 'references', []):
        if ref.get('elementType') != 'object':
            continue
        obj = objects_by_id.get(ref.get('elementId'))
        declared_stop = ref.get('type', '').lower() in ('stopline', 'stop_line')
        if declared_stop and (obj is None or not is_stop(obj)):
            raise ValueError(f'Signal {signal.id}: referenced stop-line object {ref.get("elementId")} is missing or unsupported')
        if obj is not None and is_stop(obj) and obj not in bound:
            bound.append(obj)
    return bound


def explicit_lines(road, signal, direction):
    bound = bound_stop_lines(road, signal)
    candidates = []
    for obj in bound if bound else road.objects:
        if not is_stop(obj):
            continue
        if obj.get('orientation', 'none') not in ('none', '+' if direction > 0 else '-'):
            continue
        if not bound:
            distance = direction*(number(signal.s)-number(obj.get('s')))
            if not 0 <= distance <= 30:
                continue
        candidates.append((abs(number(signal.s)-number(obj.get('s'))), obj))
    return [obj for _, obj in sorted(candidates, key=lambda pair: pair[0])], bool(bound)


def append_stop_line(pb_signal, ends):
    """Write geometry independently of lane overlap selection, once per curve."""
    coordinates = [(p.x, p.y, p.z) for p in ends]
    existing = [[(p.x, p.y, p.z) for p in c.segment[0].line_segment.point] for c in pb_signal.stop_line]
    if coordinates in existing:
        return
    curve = pb_signal.stop_line.add().segment.add()
    for point in ends:
        p = curve.line_segment.point.add()
        p.x, p.y, p.z = point.x, point.y, point.z
    curve.start_position.CopyFrom(curve.line_segment.point[0])
    curve.length = math.dist(coordinates[0], coordinates[1])


def remap_lane(road, section_id, lane, target_id):
    """Follow explicit lane links if stop line and signal occupy different sections."""
    while section_id != target_id:
        step = 1 if target_id > section_id else -1
        link = lane.link.successor if step > 0 else lane.link.predecessor
        if link is None:
            raise ValueError('Stop line crosses laneSection boundary without a lane link')
        section_id += step
        section = road.lanes.lane_sections[section_id]
        lane = next((l for l in section.left+section.right if l.lane_id == link.link_id), None)
        if lane is None or lane.lane_type != 'driving':
            raise ValueError('Stop line lane link does not resolve to a driving lane')
    return lane


def associate(converter, road, signal, pb_signal):
    from imap.lib.signal_geometry import lane_s_at
    signal_s = number(signal.s)
    index = section_at(road, signal_s)
    offset = global_var.get_element_value('stop_line_offset')
    offset = 1.0 if offset is None else offset
    pb_lanes = {p.id.id: p for p in converter.pb_map.lane}
    # All bound elements define signal.stop_line, even if no eligible lane is
    # crossed or several lines cross the same lane. Light s/t only locate the body.
    for obj in bound_stop_lines(road, signal):
        stop_s, ends = stop_object(road, obj)
        section_at(road, stop_s)
        append_stop_line(pb_signal, ends)
    for lane in lane_ids(road.lanes.lane_sections[index], signal):
        direction = 1 if int(lane.lane_id) < 0 else -1
        objects, linked = explicit_lines(road, signal, direction)
        chosen = None
        for obj in objects:
            ranges = [(int(v.get('fromLane')), int(v.get('toLane'))) for v in obj.findall('validity')]
            s, ends = stop_object(road, obj)
            target_index = section_at(road, s)
            stop_lane = remap_lane(road, index, lane, target_index)
            if ranges and not any(lo <= int(stop_lane.lane_id) <= hi for lo, hi in ranges):
                continue
            station = intersection_station(stop_lane, ends)
            if station is not None:
                chosen = target_index, stop_lane, ends, station
                break
        if chosen is None:
            if linked:
                logging.warning('Signal %s lane %s is not crossed by its explicit stop line; not associated', signal.id, lane.lane_id)
                continue
            s = max(0, min(road.length, signal_s-direction*offset))
            target_index = section_at(road, s)
            stop_lane = remap_lane(road, index, lane, target_index)
            chosen = target_index, stop_lane, [interpolate(stop_lane.left_boundary, s), interpolate(stop_lane.right_boundary, s)], lane_s_at(stop_lane, s)
        target_index, stop_lane, ends, station = chosen
        key = f'road_{road.road_id}_lane_{target_index}_{stop_lane.lane_id}'
        pb_lane = pb_lanes.get(key)
        if pb_lane is None:
            continue
        # Avoid duplicate overlaps from redundant references.
        overlap_id = f'{key}_{pb_signal.id.id}'
        if any(o.id.id == overlap_id for o in converter.pb_map.overlap):
            continue
        append_stop_line(pb_signal, ends)
        overlap = converter.pb_map.overlap.add()
        overlap.id.id = overlap_id
        info = overlap.object.add()
        info.id.id = key
        info.lane_overlap_info.start_s = info.lane_overlap_info.end_s = max(0, min(pb_lane.length, station))
        info.lane_overlap_info.is_merge = False
        info = overlap.object.add()
        info.id.id = pb_signal.id.id
        info.signal_overlap_info.SetInParent()
        pb_lane.overlap_id.add().id = overlap_id
        pb_signal.overlap_id.add().id = overlap_id


def convert_signals(converter):
    definitions = {}
    for road in converter.xodr_map.roads.values():
        for signal in road.signals.signals:
            if signal.id in definitions:
                raise ValueError(f'Duplicate OpenDRIVE signal id: {signal.id}')
            if signal.orientation not in ('+', '-', 'none'):
                raise ValueError(f'Invalid signal orientation: {signal.orientation}')
            if not signal.is_traffic_light():
                continue
            pb = converter.pb_map.signal.add()
            pb.id.id = f'signal_{road.road_id}_{signal.id}'
            body(pb, road, signal)
            definitions[signal.id] = pb
            associate(converter, road, signal, pb)
    for road in converter.xodr_map.roads.values():
        for reference in road.signals.signal_references:
            pb = definitions.get(reference.id)
            if pb is None:
                logging.warning('Unresolved or unsupported signalReference %s on road %s', reference.id, road.road_id)
                continue
            associate(converter, road, reference, pb)
