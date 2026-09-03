from __future__ import annotations

import csv
import math

import RiverNetworkTools
from AssignPointToClosestPointOnRoute import assign_point_to_closest_point_on_route


PATHPOINT_ID_FIELD = 'id'
PATHPOINT_DIST_FIELD = 'dist'
GAUGING_MEAS_FIELD = 'MEAS'
MISSING_DISCHARGE_VALUE = -999


def execute_SpatializeQ(
    route_D8,
    RID_field_D8,
    D8pathpoints,
    relate_table,
    r_flowacc,
    routes,
    links,
    RID_field,
    Qorder_field,
    Qpoints,
    id_field_Qpoints,
    RID_Qpoints,
    dist_field_Qpoints,
    AtlasReach_field_Qpoints,
    targetpoints,
    id_field_target,
    RID_field_target,
    Distance_field_target,
    DEM_field_target,
    Qcsv_file,
    output_points=None,
    messages=None,
    GIStools=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    prepared_targets = GIStools.Geoprocessing.create_points_on_route_layer(
        routes,
        RID_field,
        targetpoints,
        RID_field_target,
        Distance_field_target,
    )
    try:
        d8_info = GIStools.DataManagement.read_point_dataset(
            D8pathpoints,
            [PATHPOINT_ID_FIELD, RID_field_D8, PATHPOINT_DIST_FIELD],
        )
        sampled_d8_rows = sample_flowacc_rows(d8_info['records'], r_flowacc, GIStools=GIStools, messages=messages)
        sampled_d8_rows = attach_main_route_ids(sampled_d8_rows, relate_table, RID_field, RID_field_D8, GIStools=GIStools)

        target_info = GIStools.DataManagement.read_point_dataset(
            prepared_targets,
            [id_field_target, RID_field_target, Distance_field_target, DEM_field_target],
        )
        target_rows = assign_point_to_closest_point_on_route(
            data_points=sampled_d8_rows,
            data_fields=['flowacc'],
            data_matching_fields=[RID_field],
            target_points=target_info['records'],
            target_rid_field=RID_field_target,
            target_dist_field=Distance_field_target,
            target_matching_fields=[RID_field_target],
            stat='CLOSEST',
            messages=messages,
        )

        network = build_network(routes, links, RID_field, GIStools=GIStools, order_field=Qorder_field)

        q_info = GIStools.DataManagement.read_table_dataset(
            Qpoints,
            [id_field_Qpoints, RID_Qpoints, dist_field_Qpoints, AtlasReach_field_Qpoints],
        )
        qcollection = RiverNetworkTools.PointsCollection(network, 'Qpts')
        qcollection.dict_attr_fields['id'] = id_field_Qpoints
        qcollection.dict_attr_fields['reach_id'] = RID_Qpoints
        qcollection.dict_attr_fields['dist'] = dist_field_Qpoints
        qcollection.dict_attr_fields['AtlasID'] = AtlasReach_field_Qpoints
        qcollection.load_table(q_info['records'])

        targetcollection = RiverNetworkTools.PointsCollection(network, 'target')
        targetcollection.dict_attr_fields['id'] = id_field_target
        targetcollection.dict_attr_fields['reach_id'] = RID_field_target
        targetcollection.dict_attr_fields['dist'] = Distance_field_target
        targetcollection.dict_attr_fields['DEM'] = DEM_field_target
        targetcollection.dict_attr_fields['flowacc'] = 'flowacc'
        targetcollection.load_table(target_rows)

        _assign_reference_points_to_targets(network, qcollection, targetcollection, messages)
        q_lookup = _read_raw_discharge_lookup(Qcsv_file)
        for reach in network.browse_reaches_down_to_up():
            for targetpt in reach.browse_points(targetcollection, orientation='DOWN_TO_UP'):
                try:
                    q_lidar = float(q_lookup[str(targetpt.lastQpts.AtlasID)][str(targetpt.DEM)])
                except (KeyError, TypeError, ValueError):
                    _add_error(
                        messages,
                        'Missing line or column in the csv file: ' + str(targetpt.DEM) + ' / ' + str(targetpt.lastQpts.AtlasID),
                    )
                targetpt.Qlidar = q_lidar * flowacc_to_area_km2(targetpt.flowacc, r_flowacc)

        targetcollection.add_SavedVariable('QptsID', 'str', 20)
        targetcollection.add_SavedVariable('Qlidar', 'float')
        output_rows = targetcollection.to_table_rows()
        if output_points in [None, '']:
            return output_rows

        output_info = {
            'field_names': [id_field_target, RID_field_target, Distance_field_target, DEM_field_target],
            'field_definitions': {
                name: target_info['field_definitions'][name]
                for name in [id_field_target, RID_field_target, Distance_field_target, DEM_field_target]
                if name in target_info['field_definitions']
            },
        }
        return GIStools.DataManagement.write_output_table(
            output_points,
            output_rows,
            output_info,
            [
                {'name': 'flowacc', 'dtype': 'float'},
                {'name': 'QptsID', 'dtype': 'str', 'max_length': 20},
                {'name': 'Qlidar', 'dtype': 'float'},
            ],
        )
    except Exception as exc:
        if messages is None:
            raise
        _add_error(messages, str(exc))
    finally:
        try:
            GIStools.Geoprocessing.delete_layer(prepared_targets)
        except Exception:
            pass


def build_network(routes, links, rid_field, GIStools=None, order_field=None):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    field_names = [rid_field]
    if order_field not in [None, ''] and order_field not in field_names:
        field_names.append(order_field)
    route_features = list(GIStools.DataManagement.load_line_features(routes, field_names))
    link_rows = list(
        GIStools.DataManagement.load_table_rows(
            links,
            [
                RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD,
                RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD,
            ],
        )
    )

    network = RiverNetworkTools.RiverNetwork()
    network.dict_attr_fields['id'] = rid_field
    if order_field not in [None, '']:
        network.dict_attr_fields['order'] = order_field
    network.load_data(route_features, link_rows)
    return network


def build_target_collection(network, rid_field, rows, dem_field=None):
    targetcollection = RiverNetworkTools.PointsCollection(network, 'target')
    targetcollection.dict_attr_fields['id'] = PATHPOINT_ID_FIELD
    targetcollection.dict_attr_fields['reach_id'] = rid_field
    targetcollection.dict_attr_fields['dist'] = PATHPOINT_DIST_FIELD
    targetcollection.dict_attr_fields['flowacc'] = 'flowacc'
    if dem_field not in [None, '']:
        targetcollection.dict_attr_fields['DEM'] = dem_field
    targetcollection.load_table(rows)
    return targetcollection


def build_gauging_station_collection(
    network,
    rid_field,
    rows,
    id_field,
    name_field,
    drainage_area_field,
    discharge_field=None,
):
    qcollection = RiverNetworkTools.PointsCollection(network, 'Qpts')
    qcollection.dict_attr_fields['id'] = id_field
    qcollection.dict_attr_fields['reach_id'] = rid_field
    qcollection.dict_attr_fields['dist'] = GAUGING_MEAS_FIELD
    qcollection.dict_attr_fields['name'] = name_field
    qcollection.dict_attr_fields['drainage_area'] = drainage_area_field
    if discharge_field not in [None, '']:
        qcollection.dict_attr_fields['discharge'] = discharge_field
    qcollection.load_table(rows)
    return qcollection


def sample_flowacc_rows(rows, r_flowacc, GIStools=None, messages=None):
    if GIStools is None:
        GIStools = _autodetect_gistools()
    raster_grid = GIStools.RasterAccess.read_raster_grid(r_flowacc)
    output_rows = []
    for row in rows:
        output_row = dict(row)
        output_row['flowacc'] = sample_raster_grid(raster_grid, row.get('X'), row.get('Y'))
        output_rows.append(output_row)
    _add_message(messages, 'Sampled flow accumulation for {} point(s).'.format(len(output_rows)))
    return output_rows


def attach_main_route_ids(rows, relate_table, main_rid_field, d8_rid_field, GIStools=None):
    if GIStools is None:
        GIStools = _autodetect_gistools()
    relate_info = GIStools.DataManagement.read_table_dataset(relate_table)
    relate_main_field, relate_d8_field = resolve_relate_fields(relate_info['field_names'], main_rid_field, d8_rid_field)
    d8_to_main = {}
    for row in relate_info['records']:
        main_value = row.get(relate_main_field)
        d8_value = row.get(relate_d8_field)
        if main_value is None or d8_value is None:
            continue
        d8_to_main[int(d8_value)] = main_value

    output_rows = []
    for row in rows:
        output_row = dict(row)
        d8_value = row.get(d8_rid_field)
        output_row[main_rid_field] = None if d8_value in [None, ''] else d8_to_main.get(int(d8_value))
        output_rows.append(output_row)
    return output_rows


def build_relate_lookup(relate_table, d8_rid_field, GIStools=None):
    if GIStools is None:
        GIStools = _autodetect_gistools()
    relate_info = GIStools.DataManagement.read_table_dataset(relate_table)
    candidate_fields = [field_name for field_name in relate_info['field_names'] if str(field_name).lower() != 'part_count']
    if len(candidate_fields) < 2:
        return {}
    d8_field = None
    for field_name in candidate_fields:
        if str(field_name).lower() == str(d8_rid_field).lower():
            d8_field = field_name
            break
    if d8_field is None:
        d8_field = candidate_fields[-1]
    main_field = candidate_fields[0] if candidate_fields[0] != d8_field else candidate_fields[1]

    lookup = {}
    for row in relate_info['records']:
        d8_value = row.get(d8_field)
        if d8_value is None:
            continue
        lookup[int(d8_value)] = {
            'RID_routesmain': row.get(main_field),
            'RID_D8': row.get(d8_field),
        }
    return lookup


def resolve_relate_fields(field_names, main_rid_field, d8_rid_field=None):
    candidate_fields = [field_name for field_name in field_names if str(field_name).lower() != 'part_count']
    if len(candidate_fields) < 2:
        raise ValueError('Relate table must contain two route ID fields and PART_COUNT.')

    main_field = None
    for field_name in candidate_fields:
        if str(field_name).lower() == str(main_rid_field).lower():
            main_field = field_name
            break
    if main_field is None:
        main_field = candidate_fields[0]

    d8_field = None
    if d8_rid_field not in [None, '']:
        for field_name in candidate_fields:
            if str(field_name).lower() == str(d8_rid_field).lower():
                d8_field = field_name
                break
    if d8_field is None:
        d8_field = candidate_fields[1] if candidate_fields[0] == main_field else candidate_fields[0]
    return main_field, d8_field


def read_lidar_discharge_csv(csv_path):
    q_dict = {}
    discharges_list = []
    with open(csv_path, 'r', newline='') as csvfile:
        csvreader = csv.DictReader(csvfile)
        if csvreader.fieldnames is None or len(csvreader.fieldnames) < 2:
            raise ValueError('The discharge CSV must contain one DEM-id column and at least one station column.')
        for station in csvreader.fieldnames[1:]:
            q_dict[station] = {}
        firstrowname = csvreader.fieldnames[0]
        for line in csvreader:
            discharge_name = line[firstrowname]
            discharges_list.append(discharge_name)
            for station in csvreader.fieldnames[1:]:
                raw_value = line.get(station)
                if raw_value in [None, '']:
                    continue
                try:
                    value = float(raw_value)
                except ValueError:
                    raise ValueError('Invalid discharge value in CSV for station {} and DEM {}.'.format(station, discharge_name))
                if value not in [-999, -9999]:
                    q_dict[station][discharge_name] = value
    return q_dict, discharges_list


def flowacc_to_area_km2(flowacc_value, r_flowacc):
    return float(flowacc_value) * float(r_flowacc.meanCellWidth) * float(r_flowacc.meanCellHeight) / 1000000.0


def sample_raster_grid(raster_grid, x_value, y_value):
    if x_value in [None, ''] or y_value in [None, '']:
        return None
    col = int((float(x_value) - float(raster_grid['x_min'])) / float(raster_grid['pixel_width']))
    row = int((float(raster_grid['y_max']) - float(y_value)) / float(raster_grid['pixel_height']))
    if row < 0 or col < 0 or row >= int(raster_grid['height']) or col >= int(raster_grid['width']):
        return None
    value = raster_grid['array'][row][col]
    nodata = raster_grid.get('nodata')
    if nodata is not None:
        try:
            if math.isnan(nodata):
                if math.isnan(value):
                    return None
            elif float(value) == float(nodata):
                return None
        except Exception:
            pass
    try:
        if math.isnan(value):
            return None
    except Exception:
        pass
    return float(value)


def build_output_point_features(targetcollection, output_field_map, extra_attribute_builders=None):
    if extra_attribute_builders is None:
        extra_attribute_builders = []

    features = []
    for point in sorted(targetcollection._points.values(), key=lambda item: item.id):
        attributes = {}
        for attr_name, field_name in output_field_map.items():
            if attr_name == 'reach_id':
                attributes[field_name] = point.reach.id
            else:
                attributes[field_name] = getattr(point, attr_name)
        for field_name, builder in extra_attribute_builders:
            attributes[field_name] = builder(point)
        features.append(
            RiverNetworkTools.PointFeature(
                attributes,
                RiverNetworkTools.Coordinate(float(point.X), float(point.Y)),
            )
        )
    return features


def compute_gauging_station_discharges(
    network,
    Qcollection,
    targetcollection,
    dem_id_field,
    beta,
    cell_width,
    cell_height,
    d8_pts_data=None,
    feedback=None,
    messages=None,
    q_field=None,
):
    del dem_id_field

    class Ref_point:
        def __init__(self, name, discharges, drainage_area, reach, dist):
            self.name = name
            self.discharges = discharges
            self.drainage_area = drainage_area
            self.reach = reach
            self.dist = dist

    for reach in network.browse_reaches_down_to_up():
        for targetpt in reach.browse_points(targetcollection, orientation='DOWN_TO_UP'):
            targetpt.upQpts = {}
            targetpt.downQpts = {}
            targetpt.weightedQ = {}
            targetpt.computedQLiDAR = MISSING_DISCHARGE_VALUE

    discharges_list = list(getattr(Qcollection, '_discharges_list', []))
    for discharge in discharges_list:
        for reach in network.browse_reaches_up_to_down():
            if reach.is_upstream_end():
                lastQpts = None
            for Qpts in reach.browse_points(Qcollection, orientation='UP_TO_DOWN'):
                if discharge not in getattr(Qpts, 'discharges', {}):
                    continue
                if lastQpts is not None:
                    max_dist = lastQpts.dist if lastQpts.reach.id == reach.id else None
                    for targetpt in reach.browse_points(targetcollection, orientation='UP_TO_DOWN'):
                        if discharge not in targetpt.upQpts:
                            targetpt.upQpts[discharge] = []
                        if (max_dist is None or targetpt.dist <= max_dist) and targetpt.dist > Qpts.dist:
                            if lastQpts.name not in [pt.name for pt in targetpt.upQpts[discharge]]:
                                targetpt.upQpts[discharge].append(lastQpts)
                lastQpts = Ref_point(
                    Qpts.name,
                    dict(Qpts.discharges),
                    Qpts.drainage_area,
                    Qpts.reach,
                    Qpts.dist,
                )

            if lastQpts is not None:
                max_dist = lastQpts.dist if lastQpts.reach.id == reach.id else None
                for targetpt in reach.browse_points(targetcollection, orientation='UP_TO_DOWN'):
                    if discharge not in targetpt.upQpts:
                        targetpt.upQpts[discharge] = []
                    if max_dist is None or targetpt.dist <= max_dist:
                        if lastQpts.name not in [pt.name for pt in targetpt.upQpts[discharge]]:
                            targetpt.upQpts[discharge].append(lastQpts)

        for reach in network.browse_reaches_down_to_up():
            if feedback is not None and hasattr(feedback, 'isCanceled') and feedback.isCanceled():
                break

            lastQpts = None
            if not reach.is_downstream_end():
                down_reach = reach.get_downstream_reach()
                if hasattr(down_reach, 'upstream_calculated_Q'):
                    down_calculated_Q = down_reach.upstream_calculated_Q
                    if discharge in down_calculated_Q.discharges:
                        lastQpts = down_calculated_Q

            for Qpts in reach.browse_points(Qcollection, orientation='DOWN_TO_UP'):
                if discharge not in getattr(Qpts, 'discharges', {}):
                    continue
                if lastQpts is not None:
                    min_dist = lastQpts.dist if lastQpts.reach.id == reach.id else 0
                    for targetpt in reach.browse_points(targetcollection, orientation='DOWN_TO_UP'):
                        if targetpt.dist >= min_dist:
                            targetpt.downQpts[discharge] = lastQpts
                lastQpts = Ref_point(
                    Qpts.name,
                    dict(Qpts.discharges),
                    Qpts.drainage_area,
                    Qpts.reach,
                    Qpts.dist,
                )

            if lastQpts is not None:
                min_dist = lastQpts.dist if lastQpts.reach.id == reach.id else 0
                for targetpt in reach.browse_points(targetcollection, orientation='DOWN_TO_UP'):
                    if targetpt.dist >= min_dist:
                        targetpt.downQpts[discharge] = lastQpts

            for targetpt in reach.browse_points(targetcollection, orientation='DOWN_TO_UP'):
                localarea = _require_local_area(targetpt, cell_width, cell_height)
                uppts = targetpt.upQpts.get(discharge, [])
                downpt = targetpt.downQpts.get(discharge)

                if downpt is None:
                    for uppt in uppts:
                        uppt.interpolatedQ = uppt.discharges[discharge] * (localarea / uppt.drainage_area) ** beta
                else:
                    for uppt in uppts:
                        denominator = downpt.drainage_area ** beta - uppt.drainage_area ** beta
                        if denominator == 0:
                            uppt.interpolatedQ = MISSING_DISCHARGE_VALUE
                            continue
                        q_from_down = (
                            (localarea ** beta - uppt.drainage_area ** beta) / denominator
                        ) * downpt.discharges[discharge]
                        q_from_up = (
                            (downpt.drainage_area ** beta - localarea ** beta) / denominator
                        ) * uppt.discharges[discharge]
                        uppt.interpolatedQ = q_from_down + q_from_up

                if len(uppts) > 0:
                    totalweight = sum(uppt.drainage_area for uppt in uppts)
                    weighted_value = 0.0
                    for uppt in uppts:
                        weighted_value += uppt.interpolatedQ * uppt.drainage_area / totalweight
                    targetpt.weightedQ[discharge] = weighted_value
                elif downpt is not None:
                    targetpt.weightedQ[discharge] = downpt.discharges[discharge] * (localarea / downpt.drainage_area) ** beta

            lastuppt = reach.get_last_point(targetcollection)
            if lastuppt is None:
                continue
            lastuppt_area = _require_local_area(lastuppt, cell_width, cell_height)
            if not hasattr(reach, 'upstream_calculated_Q'):
                reach.upstream_calculated_Q = Ref_point('uppt_reach' + str(reach.id), {}, lastuppt_area, reach, lastuppt.dist)
            else:
                reach.upstream_calculated_Q.drainage_area = lastuppt_area
                reach.upstream_calculated_Q.dist = lastuppt.dist
            if discharge in lastuppt.weightedQ:
                reach.upstream_calculated_Q.discharges[discharge] = lastuppt.weightedQ[discharge]

    for reach in network.browse_reaches_down_to_up():
        for targetpt in reach.browse_points(targetcollection, orientation='DOWN_TO_UP'):
            if targetpt.DEM in targetpt.weightedQ:
                targetpt.computedQLiDAR = targetpt.weightedQ[targetpt.DEM]
            else:
                if q_field is None:
                    _add_warning(
                        messages,
                        'Missing day of discharge in the csv file: ' + str(targetpt.DEM)
                        + ' (if -999, make sure that all points on route D8 fall within a DEM footprint polygon)',
                    )
                targetpt.computedQLiDAR = MISSING_DISCHARGE_VALUE

    if d8_pts_data is not None:
        computed_by_id = {
            point.id: getattr(point, 'computedQLiDAR', MISSING_DISCHARGE_VALUE)
            for point in targetcollection._points.values()
        }
        for index, row in enumerate(d8_pts_data, start=1):
            row['computedQ'] = computed_by_id.get(index, MISSING_DISCHARGE_VALUE)
        return d8_pts_data
    return targetcollection


def _assign_reference_points_to_targets(network, qcollection, targetcollection, messages):
    for reach in network.browse_reaches_down_to_up():
        down_point = None
        down_reach = reach
        while down_point is None and not down_reach.is_downstream_end():
            down_reach = down_reach.get_downstream_reach()
            down_point = down_reach.get_last_point(targetcollection)
        if reach.is_downstream_end() or down_point is None or not hasattr(down_point, 'lastQpts'):
            lastQpts = None
        else:
            lastQpts = down_point.lastQpts

        for Qpts in reach.browse_points(qcollection, orientation='DOWN_TO_UP'):
            if lastQpts is not None:
                min_dist = lastQpts.dist if lastQpts.reach.id == reach.id else 0
                for targetpt in reach.browse_points(targetcollection, orientation='DOWN_TO_UP'):
                    if targetpt.dist >= min_dist and targetpt.dist < Qpts.dist:
                        targetpt.lastQpts = lastQpts
                        targetpt.QptsID = str(lastQpts.AtlasID)
            lastQpts = Qpts

        if lastQpts is not None:
            min_dist = lastQpts.dist if lastQpts.reach.id == reach.id else 0
            for targetpt in reach.browse_points(targetcollection, orientation='DOWN_TO_UP'):
                if targetpt.dist >= min_dist:
                    targetpt.lastQpts = lastQpts
                    targetpt.QptsID = str(lastQpts.AtlasID)

    for reach in network.browse_reaches_up_to_down(prioritize_reach_attribute='order', reverse=True):
        if reach.is_upstream_end():
            lastQpts = None
        for Qpts in reach.browse_points(qcollection, orientation='UP_TO_DOWN'):
            lastQpts = Qpts
        if lastQpts is not None:
            for targetpt in reach.browse_points(targetcollection, orientation='UP_TO_DOWN'):
                if not hasattr(targetpt, 'lastQpts'):
                    targetpt.lastQpts = lastQpts
                    targetpt.QptsID = str(lastQpts.AtlasID)

    for reach in network.browse_reaches_down_to_up():
        for targetpt in reach.browse_points(targetcollection, orientation='DOWN_TO_UP'):
            if not hasattr(targetpt, 'lastQpts'):
                _add_error(messages, 'Points without an upstream or downstream discharge point on reach ' + str(reach.id))


def _require_local_area(point, cell_width, cell_height):
    flowacc = getattr(point, 'flowacc', None)
    if flowacc in [None, '']:
        raise ValueError('Flow accumulation is missing for point {}.'.format(getattr(point, 'id', '?')))
    return float(flowacc) * float(cell_width) * float(cell_height) / 1000000.0


def _read_raw_discharge_lookup(csv_path):
    lookup = {}
    with open(csv_path, 'r', newline='') as csvfile:
        csvreader = csv.DictReader(csvfile)
        firstrowname = csvreader.fieldnames[0]
        for line in csvreader:
            lookup[line[firstrowname]] = line
    return lookup


def _autodetect_gistools():
    try:
        import ArcGIStools
        return ArcGIStools
    except Exception:
        pass
    try:
        import QGIStools
        return QGIStools
    except Exception:
        pass
    raise ValueError('A GIStools package must be provided.')


def _add_message(messages, message):
    if messages is not None:
        messages.add_message(message)


def _add_warning(messages, message):
    if messages is not None:
        messages.add_warning(message)


def _add_error(messages, message):
    if messages is not None:
        messages.add_error(message)
    raise RuntimeError(message)
