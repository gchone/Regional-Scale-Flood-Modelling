from __future__ import annotations

from SpatializeQ import (
    PATHPOINT_DIST_FIELD,
    PATHPOINT_ID_FIELD,
    build_gauging_station_collection,
    build_network,
    build_output_point_features,
    build_target_collection,
    compute_gauging_station_discharges,
    sample_flowacc_rows,
    _add_message,
    _autodetect_gistools,
)


def execute_SpatializeQFloodFromGaugingStations(
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
    Q_field,
    beta_coef,
    output_points=None,
    messages=None,
    GIStools=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    d8_info = GIStools.DataManagement.read_point_dataset(
        D8pathpoints,
        [PATHPOINT_ID_FIELD, RID_field_D8, PATHPOINT_DIST_FIELD],
    )
    d8_rows = sample_flowacc_rows(d8_info['records'], r_flowacc, GIStools=GIStools, messages=messages)
    network = build_network(routes_D8, links_D8, RID_field_D8, GIStools=GIStools)
    targetcollection = build_target_collection(network, RID_field_D8, d8_rows)

    q_info = GIStools.Geoprocessing.locate_features_along_routes_records(
        Qpoints,
        routes_D8,
        RID_field_D8,
        points_tol,
        [id_field_Qpoints, name_field_Qpoints, drainage_area_field_Qpoints, Q_field],
    )
    qcollection = build_gauging_station_collection(
        network,
        RID_field_D8,
        q_info['records'],
        id_field_Qpoints,
        name_field_Qpoints,
        drainage_area_field_Qpoints,
        discharge_field=Q_field,
    )
    qcollection._discharges_list = [Q_field]
    for reach in network.browse_reaches_down_to_up():
        for qpt in reach.browse_points(qcollection, orientation='DOWN_TO_UP'):
            qpt.discharges = {Q_field: qpt.discharge}
        for targetpt in reach.browse_points(targetcollection, orientation='DOWN_TO_UP'):
            targetpt.DEM = Q_field

    targetcollection.add_SavedVariable('computedQLiDAR', 'float', field_name=Q_field)
    compute_gauging_station_discharges(
        network,
        qcollection,
        targetcollection,
        'DEM',
        float(beta_coef),
        float(r_flowacc.meanCellWidth),
        float(r_flowacc.meanCellHeight),
        messages=messages,
        q_field=Q_field,
    )

    features = build_output_point_features(
        targetcollection,
        {
            'id': PATHPOINT_ID_FIELD,
            'reach_id': RID_field_D8,
            'dist': PATHPOINT_DIST_FIELD,
            'flowacc': 'flowacc',
            'computedQLiDAR': Q_field,
        },
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
    result = GIStools.DataManagement.write_point_features(
        output_points,
        features,
        input_info,
        extra_fields=[
            {'name': 'flowacc', 'dtype': 'float'},
            {'name': Q_field, 'dtype': 'float'},
        ],
        spatial_reference=d8_info.get('spatial_reference'),
    )
    _add_message(messages, 'Created {} flood-spatialized D8 point(s).'.format(len(features)))
    return result
