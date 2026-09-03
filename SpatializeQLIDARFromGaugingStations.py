from __future__ import annotations

from SpatializeQ import (
    PATHPOINT_DIST_FIELD,
    PATHPOINT_ID_FIELD,
    build_gauging_station_collection,
    build_network,
    build_output_point_features,
    build_relate_lookup,
    build_target_collection,
    compute_gauging_station_discharges,
    read_lidar_discharge_csv,
    sample_flowacc_rows,
    _add_error,
    _add_message,
    _autodetect_gistools,
)


def execute_SpatializeQLIDARFromGaugingStations(
    routes_D8,
    links_D8,
    RID_field_D8,
    D8pathpoints,
    r_flowacc,
    Qpoints,
    id_field_Qpoints,
    name_field_Qpoints,
    drainage_area_field_Qpoints,
    points_tol,
    Qcsv_file,
    DEM_footprints,
    DEM_id_field,
    beta_coef,
    relatetable,
    output_points=None,
    messages=None,
    GIStools=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    d8_info = GIStools.Geoprocessing.join_polygon_field_to_points_records(
        D8pathpoints,
        DEM_footprints,
        DEM_id_field,
        [PATHPOINT_ID_FIELD, RID_field_D8, PATHPOINT_DIST_FIELD],
    )
    d8_rows = sample_flowacc_rows(d8_info['records'], r_flowacc, GIStools=GIStools, messages=messages)
    network = build_network(routes_D8, links_D8, RID_field_D8, GIStools=GIStools)
    targetcollection = build_target_collection(network, RID_field_D8, d8_rows, dem_field=DEM_id_field)

    q_info = GIStools.Geoprocessing.locate_features_along_routes_records(
        Qpoints,
        routes_D8,
        RID_field_D8,
        points_tol,
        [id_field_Qpoints, name_field_Qpoints, drainage_area_field_Qpoints],
    )
    qcollection = build_gauging_station_collection(
        network,
        RID_field_D8,
        q_info['records'],
        id_field_Qpoints,
        name_field_Qpoints,
        drainage_area_field_Qpoints,
    )

    station_discharges, discharges_list = read_lidar_discharge_csv(Qcsv_file)
    qcollection._discharges_list = discharges_list
    for reach in network.browse_reaches_down_to_up():
        for qpt in reach.browse_points(qcollection, orientation='DOWN_TO_UP'):
            if qpt.name not in station_discharges:
                _add_error(messages, 'Missing gauging station in the csv file: ' + str(qpt.name))
            qpt.discharges = station_discharges[qpt.name]

    targetcollection.add_SavedVariable('computedQLiDAR', 'float')
    compute_gauging_station_discharges(
        network,
        qcollection,
        targetcollection,
        DEM_id_field,
        float(beta_coef),
        float(r_flowacc.meanCellWidth),
        float(r_flowacc.meanCellHeight),
        messages=messages,
    )

    relate_lookup = {}
    if relatetable not in [None, '']:
        relate_lookup = build_relate_lookup(relatetable, RID_field_D8, GIStools=GIStools)

    features = build_output_point_features(
        targetcollection,
        {
            'id': PATHPOINT_ID_FIELD,
            'reach_id': RID_field_D8,
            'dist': PATHPOINT_DIST_FIELD,
            'flowacc': 'flowacc',
            'DEM': DEM_id_field,
            'computedQLiDAR': 'computedQLiDAR',
        },
        extra_attribute_builders=[] if not relate_lookup else [
            ('RID_routesmain', lambda point: relate_lookup.get(point.reach.id, {}).get('RID_routesmain')),
            ('RID_D8', lambda point: relate_lookup.get(point.reach.id, {}).get('RID_D8')),
        ],
    )

    if output_points in [None, '']:
        rows = []
        for feature in features:
            row = dict(feature.attributes)
            row['X'] = feature.point.x
            row['Y'] = feature.point.y
            rows.append(row)
        return rows

    input_info = {
        'field_names': [PATHPOINT_ID_FIELD, RID_field_D8, PATHPOINT_DIST_FIELD],
        'field_definitions': {
            name: d8_info['field_definitions'][name]
            for name in [PATHPOINT_ID_FIELD, RID_field_D8, PATHPOINT_DIST_FIELD]
            if name in d8_info['field_definitions']
        },
    }
    extra_fields = [
        {'name': 'flowacc', 'dtype': 'float'},
        {
            'name': DEM_id_field,
            'field_definition': d8_info['field_definitions'].get(DEM_id_field),
            'dtype': 'str',
        },
        {'name': 'computedQLiDAR', 'dtype': 'float'},
    ]
    if relate_lookup:
        extra_fields.extend([
            {'name': 'RID_routesmain', 'dtype': 'int'},
            {'name': 'RID_D8', 'dtype': 'int'},
        ])

    result = GIStools.DataManagement.write_point_features(
        output_points,
        features,
        input_info,
        extra_fields=extra_fields,
        spatial_reference=d8_info.get('spatial_reference'),
    )
    _add_message(messages, 'Created {} LiDAR-spatialized D8 point(s).'.format(len(features)))
    return result
