"""Regressions use real protobuf messages loaded from this checkout's schemas."""
import math
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'modules/map/apollo_map'))
from proto_loader import load_map_protos
load_map_protos(ROOT)
from imap import global_var
from imap.lib.convertor import Opendrive2Apollo
from modules.common_msgs.map_msgs import map_pb2


def fixture(s=55, orientation='+', validity='-2', sections=(0, 30)):
    root = ET.Element('OpenDRIVE')
    header = ET.SubElement(root, 'header', revMajor='1', revMinor='8')
    ET.SubElement(header, 'geoReference').text = '+proj=tmerc +lat_0=31 +lon_0=121 +k=1 +x_0=0 +y_0=0 +datum=WGS84 +units=m'
    road = ET.SubElement(root, 'road', id='r', junction='-1', length='100')
    plan = ET.SubElement(road, 'planView')
    geometry = ET.SubElement(plan, 'geometry', s='0', x='100', y='50', hdg='0', length='100')
    ET.SubElement(geometry, 'line')
    elevation = ET.SubElement(road, 'elevationProfile')
    ET.SubElement(elevation, 'elevation', s='0', a='2', b='0.1', c='0', d='0')
    lanes = ET.SubElement(road, 'lanes')
    ET.SubElement(lanes, 'laneOffset', s='0', a='1', b='0', c='0', d='0')
    for start in sections:
        section = ET.SubElement(lanes, 'laneSection', s=str(start))
        center = ET.SubElement(section, 'center')
        ET.SubElement(ET.SubElement(center, 'lane', id='0', type='none'), 'roadMark', sOffset='0', type='solid', color='yellow')
        for name, ids in [('left', [2, 1]), ('right', [-1, -2])]:
            side = ET.SubElement(section, name)
            for n in ids:
                lane = ET.SubElement(side, 'lane', id=str(n), type='driving')
                link = ET.SubElement(lane, 'link')
                ET.SubElement(link, 'predecessor', id=str(n))
                ET.SubElement(link, 'successor', id=str(n))
                ET.SubElement(lane, 'width', sOffset='0', a='3.5', b='0', c='0', d='0')
                ET.SubElement(lane, 'roadMark', sOffset='0', type='broken', color='white')
    signal = ET.SubElement(ET.SubElement(road, 'signals'), 'signal', id='light', s=str(s), t='-8',
                          orientation=orientation, country='OpenDRIVE', type='1000001', subtype='-1',
                          height='1.2', width='0.45', zOffset='3', hOffset='0', pitch='0', roll='0')
    if validity is not None:
        ET.SubElement(signal, 'validity', fromLane=validity, toLane=validity)
    return root, road, signal


class SignalConversionTest(unittest.TestCase):
    def convert(self, root, sampling=1, offset=1):
        global_var._init()
        for key, value in [('sampling_length', sampling), ('stop_line_offset', offset),
                           ('visualize', False), ('enable_z_axis', True)]:
            global_var.set_element_vaule(key, value)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'input.xodr'
            ET.ElementTree(root).write(path)
            c = Opendrive2Apollo(str(path), str(Path(temp) / 'base_map.bin'))
            c.set_parameters(False)
            c.convert()
            with contextlib.redirect_stdout(io.StringIO()):
                c.save_map()
            result = map_pb2.Map()
            result.ParseFromString((Path(temp) / 'base_map.bin').read_bytes())
            # Independently loaded source schemas must read the bundled runtime's wire format.
            self.assertEqual(result.SerializeToString(), c.pb_map.SerializeToString())
            return result

    def test_signal_station_and_offset_change_stopline_not_road_endpoint(self):
        for sampling in (0.5, 1, 3):
            for station in (55, 75):
                pb = self.convert(fixture(station)[0], sampling)
                points = pb.signal[0].stop_line[0].segment[0].line_segment.point
                self.assertAlmostEqual(points[0].x, 100+station-1)
                self.assertNotAlmostEqual(points[0].x, 200)
                self.assertAlmostEqual(points[0].y, 47.5)
                self.assertAlmostEqual(points[1].y, 44)
        pb = self.convert(fixture()[0], offset=2.5)
        self.assertAlmostEqual(pb.signal[0].stop_line[0].segment[0].line_segment.point[0].x, 152.5)

    def test_local_section_length_overlap_presence_and_body(self):
        pb = self.convert(fixture()[0])
        self.assertEqual(len(pb.signal), 1)
        self.assertEqual(len(pb.overlap), 1)
        lane_info, signal_info = pb.overlap[0].object
        self.assertEqual(lane_info.id.id, 'road_r_lane_1_-2')
        self.assertEqual(lane_info.WhichOneof('overlap_info'), 'lane_overlap_info')
        self.assertEqual(signal_info.WhichOneof('overlap_info'), 'signal_overlap_info')
        self.assertAlmostEqual(lane_info.lane_overlap_info.start_s, 24*math.sqrt(1.01))
        self.assertEqual(lane_info.lane_overlap_info.start_s, lane_info.lane_overlap_info.end_s)
        lane = next(l for l in pb.lane if l.id.id == lane_info.id.id)
        self.assertAlmostEqual(lane.length, 70*math.sqrt(1.01))
        self.assertAlmostEqual(lane.left_sample[0].s, 0)
        self.assertAlmostEqual(lane.left_sample[-1].s, lane.length)
        center = pb.signal[0].subsignal[0].location
        self.assertAlmostEqual(center.x, 155)
        self.assertAlmostEqual(center.y, 42)  # no laneOffset applied to the light
        self.assertAlmostEqual(center.z, 11.1)
        self.assertEqual(len(pb.signal[0].boundary.point), 4)

    def test_reverse_direction_multiple_validities_and_section_boundary(self):
        root, _, signal = fixture(55, '-', '1')
        ET.SubElement(signal, 'validity', fromLane='2', toLane='2')
        pb = self.convert(root)
        self.assertEqual(len(pb.overlap), 2)
        for overlap in pb.overlap:
            self.assertIn(overlap.object[0].id.id, ('road_r_lane_1_1', 'road_r_lane_1_2'))
            self.assertAlmostEqual(overlap.object[0].lane_overlap_info.start_s, 44*math.sqrt(1.01))
        pb = self.convert(fixture(30.5)[0])
        self.assertEqual(pb.overlap[0].object[0].id.id, 'road_r_lane_0_-2')
        self.assertAlmostEqual(pb.overlap[0].object[0].lane_overlap_info.start_s, 29.5*math.sqrt(1.01))

    def test_explicit_object_outline_wins_over_signal_station(self):
        for signal_s in (55, 80):
            root, road, signal = fixture(signal_s)
            obj = ET.SubElement(ET.SubElement(road, 'objects'), 'object', id='stop', type='roadMark', subtype='signalLines',
                                s='40', t='-4.25', hdg='0', zOffset='0', length='0.4', width='7')
            outline = ET.SubElement(ET.SubElement(obj, 'outlines'), 'outline')
            for u, v in [(-.2,-3.5), (.2,-3.5), (.2,3.5), (-.2,3.5)]:
                ET.SubElement(outline, 'cornerLocal', u=str(u), v=str(v), z='0')
            ET.SubElement(signal, 'reference', elementType='object', elementId='stop', type='stopLine')
            pb = self.convert(root)
            self.assertAlmostEqual(pb.signal[0].stop_line[0].segment[0].line_segment.point[0].x, 140)
            self.assertAlmostEqual(pb.overlap[0].object[0].lane_overlap_info.start_s, 10*math.sqrt(1.01))

    def test_projection_matches_source_and_bridge_frame(self):
        root, _, _ = fixture()
        projection = root.find('./header/geoReference').text
        pb = self.convert(root)
        self.assertEqual(pb.header.projection.proj, projection)
        p = pb.lane[0].central_curve.segment[0].line_segment.point[0]
        self.assertAlmostEqual(p.x, 130)
        root.find('header').remove(root.find('./header/geoReference'))
        self.assertEqual(self.convert(root).header.projection.proj, '')

    def test_bound_line_ignores_nearer_unbound_line_and_fallback_offset(self):
        for light_s in (55, 85):
            for line_s in (40, 45):
                root, road, signal = fixture(light_s)
                objects = ET.SubElement(road, 'objects')
                ET.SubElement(objects, 'object', id='bound', type='roadMark', subtype='signalLines',
                              s=str(line_s), t='-4.25', width='3.5', zOffset='0.2')
                ET.SubElement(objects, 'object', id='closer', type='roadMark', subtype='signalLines',
                              s=str(light_s-1), t='-4.25', width='3.5')
                ET.SubElement(signal, 'reference', elementType='object', elementId='bound', type='stopline')
                result = self.convert(root, offset=10)
                points = result.signal[0].stop_line[0].segment[0].line_segment.point
                self.assertEqual(len(result.signal[0].stop_line), 1)
                self.assertAlmostEqual(points[0].x, 100+line_s)
                self.assertAlmostEqual(points[0].y, 44)
                self.assertAlmostEqual(points[1].y, 47.5)
                self.assertAlmostEqual(points[0].z, 2+line_s*.1+.2)
                self.assertAlmostEqual(result.overlap[0].object[0].lane_overlap_info.start_s,
                                       (line_s-30)*math.sqrt(1.01))

    def test_all_bound_lines_are_exported_even_on_same_lane(self):
        root, road, signal = fixture()
        objects = ET.SubElement(road, 'objects')
        for i, s in enumerate((40, 45)):
            ET.SubElement(objects, 'object', id=str(i), type='roadMark', subtype='signalLines',
                          s=str(s), t='-4.25', width='3.5')
            # Redundant bindings must not duplicate geometry.
            for _ in range(2):
                ET.SubElement(signal, 'reference', elementType='object', elementId=str(i), type='stopline')
        result = self.convert(root)
        self.assertEqual(len(result.signal[0].stop_line), 2)
        self.assertEqual({curve.segment[0].line_segment.point[0].x for curve in result.signal[0].stop_line}, {140, 145})
        self.assertEqual(len(result.overlap), 1)
        self.assertAlmostEqual(result.overlap[0].object[0].lane_overlap_info.start_s, 15*math.sqrt(1.01))

    def test_bound_geometry_preserved_without_lane_intersection_or_applicability(self):
        for validity in ('-2', '-99'):
            root, road, signal = fixture(validity=validity)
            ET.SubElement(ET.SubElement(road, 'objects'), 'object', id='stop', type='roadMark', subtype='signalLines',
                          s='40', t='-20', width='3')
            ET.SubElement(signal, 'reference', elementType='object', elementId='stop', type='stopline')
            result = self.convert(root)
            self.assertEqual(len(result.signal[0].stop_line), 1)
            self.assertEqual(len(result.overlap), 0)
            self.assertAlmostEqual(result.signal[0].stop_line[0].segment[0].line_segment.point[0].x, 140)

    def test_both_directions_use_their_bound_stop_lines(self):
        root, road, signal = fixture(55, 'none', None)
        objects = ET.SubElement(road, 'objects')
        for name, orientation, t, s in [('forward', '+', '-4.25', '50'), ('reverse', '-', '6.25', '60')]:
            ET.SubElement(objects, 'object', id=name, type='roadMark', subtype='signalLines',
                          orientation=orientation, s=s, t=t, width='7')
            ET.SubElement(signal, 'reference', elementType='object', elementId=name, type='stopline')
        result = self.convert(root)
        self.assertEqual(len(result.signal[0].stop_line), 2)
        self.assertEqual(len(result.overlap), 4)
        for overlap in result.overlap:
            lane = overlap.object[0]
            expected = 20 if lane.id.id.endswith(('_-1', '_-2')) else 40
            self.assertAlmostEqual(lane.lane_overlap_info.start_s, expected*math.sqrt(1.01))

    def test_every_bound_reference_must_resolve_including_partial_failure(self):
        for invalid in ('missing', 'wrong_type', 'zero_width', 'outside_road'):
            root, road, signal = fixture()
            objects = ET.SubElement(road, 'objects')
            ET.SubElement(objects, 'object', id='valid', type='roadMark', subtype='signalLines', s='40', t='-4.25', width='7')
            ET.SubElement(signal, 'reference', elementType='object', elementId='valid', type='stopline')
            if invalid != 'missing':
                ET.SubElement(objects, 'object', id='invalid', type='crosswalk' if invalid == 'wrong_type' else 'roadMark',
                              subtype='signalLines', s='101' if invalid == 'outside_road' else '45', t='-4.25',
                              width='0' if invalid == 'zero_width' else '7')
            ET.SubElement(signal, 'reference', elementType='object', elementId='invalid', type='stopline')
            with self.assertRaises(ValueError, msg=invalid):
                self.convert(root)

    def test_tilt_rotates_body_without_moving_stop_line(self):
        root, _, signal = fixture()
        original = self.convert(root)
        signal.set('hOffset', '1.2'); signal.set('pitch', '0.2'); signal.set('roll', '0.3')
        tilted = self.convert(root)
        self.assertEqual(tilted.signal[0].stop_line, original.signal[0].stop_line)
        self.assertNotEqual(tilted.signal[0].boundary, original.signal[0].boundary)

    def test_curved_reference_interpolates_stopline_and_keeps_signal_t(self):
        root, road, _ = fixture()
        geometry = road.find('./planView/geometry')
        geometry.remove(geometry.find('line'))
        ET.SubElement(geometry, 'arc', curvature='0.01')
        result = self.convert(root)
        first = result.signal[0].stop_line[0].segment[0].line_segment.point[0]
        self.assertAlmostEqual(first.x, 100+102.5*math.sin(0.54))
        self.assertAlmostEqual(first.y, 50+100*(1-math.cos(0.54))-2.5*math.cos(0.54))
        center = result.signal[0].subsignal[0].location
        self.assertAlmostEqual(center.x, 100+108*math.sin(0.55))
        self.assertAlmostEqual(center.y, 50+100*(1-math.cos(0.55))-8*math.cos(0.55))

    def test_current_straight_map_and_signal_references(self):
        root = ET.parse(ROOT / 'modules/map/apollo_map/opendrive/straight_map/straight.xodr').getroot()
        original = self.convert(root)
        signal = root.find('./road/signals/signal')
        signal.set('s', str(float(signal.get('s'))+10))
        changed = self.convert(root)
        a = original.signal[0].stop_line[0].segment[0].line_segment.point[0]
        b = changed.signal[0].stop_line[0].segment[0].line_segment.point[0]
        bound_ids = {r.get('elementId') for r in signal.findall('reference') if r.get('elementType') == 'object'}
        bound = [o for o in root.findall('./road/objects/object') if o.get('id') in bound_ids]
        if bound:
            self.assertEqual(original.signal[0].stop_line, changed.signal[0].stop_line)
            bound[0].set('s', str(float(bound[0].get('s'))+5))
            moved = self.convert(root).signal[0].stop_line[0].segment[0].line_segment.point[0]
            self.assertAlmostEqual(math.hypot(moved.x-a.x, moved.y-a.y), 5, places=4)
        else:
            self.assertAlmostEqual(math.hypot(b.x-a.x, b.y-a.y), 10, places=4)
        root, road, signal = fixture()
        # Reference on the same road adds applicability to the other carriageway.
        ref = ET.SubElement(road.find('signals'), 'signalReference', id='light', s='60', t='5', orientation='-')
        ET.SubElement(ref, 'validity', fromLane='1', toLane='1')
        result = self.convert(root)
        self.assertEqual(len(result.signal), 1)
        self.assertEqual(len(result.overlap), 2)

    def test_unlinked_corner_road_stopline_and_none_orientation(self):
        root, road, signal = fixture(55, 'none', None)
        obj = ET.SubElement(ET.SubElement(road, 'objects'), 'object', id='s', type='roadMark', subtype='signalLines',
                            s='48', t='-2', orientation='+')
        outline = ET.SubElement(ET.SubElement(obj, 'outlines'), 'outline')
        for s, t in [(47.8,-6), (48.2,-6), (48.2,1), (47.8,1)]:
            ET.SubElement(outline, 'cornerRoad', s=str(s), t=str(t), dz='0')
        result = self.convert(root)
        self.assertEqual(len(result.overlap), 4)
        # Right-side lanes share one explicit line; reverse traffic has fallback lines.
        self.assertEqual(len(result.signal[0].stop_line), 3)
        for overlap in result.overlap:
            lane = overlap.object[0]
            expected = 18 if lane.id.id.endswith(('-1', '-2')) else 44
            self.assertAlmostEqual(lane.lane_overlap_info.start_s, expected*math.sqrt(1.01))

    def test_reference_on_another_road_uses_that_roads_lane_station(self):
        root, _, _ = fixture()
        other_root, other_road, other_signal = fixture(20, '-', '1', sections=(0,))
        other_road.set('id', 'other')
        signals = other_road.find('signals'); signals.remove(other_signal)
        ref = ET.SubElement(signals, 'signalReference', id='light', s='20', t='6', orientation='-')
        ET.SubElement(ref, 'validity', fromLane='1', toLane='1')
        root.append(other_road)
        result = self.convert(root)
        self.assertEqual(len(result.signal), 1)
        lane_info = result.overlap[-1].object[0]
        self.assertEqual(lane_info.id.id, 'road_other_lane_0_1')
        self.assertAlmostEqual(lane_info.lane_overlap_info.start_s, 79*math.sqrt(1.01))

    def test_explicit_stop_line_does_not_control_lanes_it_does_not_cross(self):
        root, road, signal = fixture(55, '+', None)
        ET.SubElement(ET.SubElement(road, 'objects'), 'object', id='stop', type='roadMark', subtype='signalLines',
                      s='50', t='-4.25', width='3.5')
        ET.SubElement(signal, 'reference', elementType='object', elementId='stop', type='stopLine')
        result = self.convert(root)
        self.assertEqual(len(result.overlap), 1)
        self.assertTrue(result.overlap[0].object[0].id.id.endswith('_-2'))

    def test_unsupported_frames_and_missing_cross_section_links_fail_explicitly(self):
        for kind in ('lht', 'offset', 'lane_direction', 'missing_link'):
            root, road, _ = fixture(30.5)
            if kind == 'lht': road.set('rule', 'LHT')
            if kind == 'offset': ET.SubElement(root.find('header'), 'offset', x='100', y='0', z='0', hdg='0')
            if kind == 'lane_direction': road.find('./lanes/laneSection/right/lane').set('direction', 'reversed')
            if kind == 'missing_link':
                for link in road.findall('./lanes/laneSection/right/lane/link'):
                    for child in list(link): link.remove(child)
            with self.assertRaises(ValueError, msg=kind):
                self.convert(root)


if __name__ == '__main__':
    unittest.main()
