import math
import warnings

import numpy as np
import scipy.optimize
import scipy.sparse
from scipy.interpolate import interp1d
from scipy.optimize import minimize_scalar
from scipy.stats import norm

import RiverNetworkTools
from rdp import rdp


def get_lower_bound(sd2, default=0.001):
    lower_bound = default
    while lower_bound >= sd2:
        lower_bound = 10 ** (math.floor(math.log10(lower_bound)) - 1)
    return lower_bound


def QuantileCarving(listcs, prevcs, messages, tau=0.5):
    if len(listcs) == 0:
        return

    if prevcs is None:
        minz = -math.inf
    else:
        minz = prevcs.zws_quantilecarving

    x = _build_continuous_distance_array(listcs)
    z = np.array([max(cs.z_forws, minz) for cs in listcs], dtype=float)

    n = len(listcs)
    ix = range(1, n)
    ixc = range(0, n - 1)

    f = [tau * np.ones((n, 1)), (1 - tau) * np.ones((n, 1)), np.zeros((n, 1))]
    f = np.vstack(f).ravel()

    Aeq = scipy.sparse.hstack([scipy.sparse.identity(n), -scipy.sparse.identity(n), scipy.sparse.identity(n)])
    beq = z

    lb = [0.0] * (2 * n)
    lb.extend([-math.inf] * n)
    bounds = [(lower, None) for lower in lb]

    if n > 1:
        d = 1.0 / (x[list(ix)] - x[list(ixc)])
        Atmp2 = scipy.sparse.coo_matrix((d, (list(ix), list(ixc))), shape=(n, n)) - scipy.sparse.coo_matrix(
            (d, (list(ix), list(ix))),
            shape=(n, n),
        )
    else:
        Atmp2 = scipy.sparse.csr_matrix((n, n))
    Atmp = scipy.sparse.csr_matrix((n, n * 2))
    A = scipy.sparse.hstack([Atmp, Atmp2])
    b = np.zeros(n)

    output = scipy.optimize.linprog(f, A, b, Aeq, beq, bounds=bounds, method="highs", callback=None)

    if output.status > 0:
        _add_warning(messages, "Quantile regression failure, check results for potential obvious error")
    if output.x is None:
        newz = z
    else:
        newz = output.x[-n:]

    for index, cs in enumerate(listcs):
        cs.zws_quantilecarving = float(newz[index])


def Gaussian_weighted_moving_average(
    listcs,
    prev_cs,
    sigma,
    uncertaintysigma,
    uncertaintyfactor,
    slopesigma,
    slopefactor,
):
    if len(listcs) == 0:
        return

    if prev_cs is None:
        minz = -math.inf
    else:
        minz = prev_cs.zws_smoothed

    distances = _build_continuous_distance_array(listcs)
    values = np.array([max(cs.zws_quantilecarving, minz) for cs in listcs], dtype=float)
    unbreached_values = np.array([cs.z_forws for cs in listcs], dtype=float)

    carving = unbreached_values - values
    smoothed_values = np.zeros_like(values)
    uncertainty_vec = np.zeros_like(values)
    restricted = np.zeros_like(values)
    sd2_vec = np.zeros_like(values)
    local_sigma_vec = np.zeros_like(values)
    sd2 = None

    for i in range(len(values)):
        local_sigma = min(sigma, (distances[i] - distances[0]) * 5.0)
        local_sigma = max(local_sigma, 10.0)
        local_sigma_vec[i] = local_sigma

        weights = norm.pdf(distances, loc=distances[i], scale=uncertaintysigma)
        weights /= weights.sum()
        corrections = sum(np.abs(carving) * weights) ** uncertaintyfactor
        if corrections < 1e-9:
            smoothed_values[i] = values[i]
            sd2 = None
        else:
            weightsslope = norm.pdf(distances, loc=distances[i], scale=slopesigma)
            weightsslope /= weightsslope.sum()
            deltaz = math.exp(sum(np.abs(values[i] - values) * weightsslope)) ** slopefactor
            uncertainty = corrections / deltaz
            uncertainty_vec[i] = uncertainty

            if i > 0:
                x_values = distances[0 : i - 1]
                mu1 = distances[i - 1]
                if sd2 is not None:
                    sd1 = sd2
                    sd2 = uncertainty * local_sigma
                    mu2 = distances[i]
                    F1 = norm.pdf(x_values, loc=mu1, scale=sd1)
                    F2 = norm.pdf(x_values, loc=mu2, scale=sd2)
                    validpdf = np.all(F1 >= F2)
                    if not validpdf:
                        restricted[i] = 1

                        def objective(tested_sd2):
                            F1_test = norm.pdf(x_values, loc=mu1, scale=sd1)
                            F2_test = norm.pdf(x_values, loc=mu2, scale=tested_sd2)
                            diff = F1_test - F2_test
                            if np.any(diff < 0):
                                return np.inf
                            return -tested_sd2

                        with warnings.catch_warnings():
                            warnings.filterwarnings("ignore", category=RuntimeWarning)
                            result = minimize_scalar(
                                objective,
                                bounds=(get_lower_bound(sd2), sd2),
                                method="bounded",
                            )
                            if result.success:
                                sd2 = result.x
                            else:
                                sd2 = sd1
                                restricted[i] = 2
                else:
                    sd2 = uncertainty * local_sigma
            else:
                sd2 = uncertainty * local_sigma

            sd2_vec[i] = sd2
            weights = norm.pdf(distances, loc=distances[i], scale=sd2)
            weights /= weights.sum()
            smoothed_values[i] = np.sum(weights * values)

            if i > 0 and smoothed_values[i] < smoothed_values[i - 1]:
                smoothed_values[i] = smoothed_values[i - 1]
                restricted[i] = restricted[i] + 10

    for i, cs in enumerate(listcs):
        cs.zws_smoothed = float(smoothed_values[i])
        cs.ws_uncertainty = float(uncertainty_vec[i])
        cs.restricted = float(restricted[i])
        cs.sd2 = float(sd2_vec[i])
        cs.local_sigma = float(local_sigma_vec[i])


def rdp_simplify_and_resample(listcs, epsilon=0.03):
    if len(listcs) == 0:
        return listcs

    distances = _build_continuous_distance_array(listcs)
    values = np.array([cs.zws_quantilecarving for cs in listcs], dtype=float)
    points = np.column_stack((distances, values))
    simplified_points = _rdp(points, epsilon=epsilon)
    if simplified_points.ndim == 1:
        simplified_points = simplified_points.reshape(1, -1)

    simplified_distances = simplified_points[:, 0]
    simplified_values = simplified_points[:, 1]
    if len(simplified_distances) > 1:
        interp_func = interp1d(
            simplified_distances,
            simplified_values,
            kind="linear",
            bounds_error=False,
            fill_value="extrapolate",
        )
        resampled_values = interp_func(distances)
    else:
        resampled_values = np.full_like(values, simplified_values[0])

    for index, cs in enumerate(listcs):
        cs.zws_quantilecarving = float(resampled_values[index])
    return listcs


def execute_WSprocessing(
    network_shp,
    links_table,
    RID_field,
    order_field,
    datapoints,
    id_field_pts,
    RID_field_pts,
    Distance_field_pts,
    dem_forws_field,
    DEM_ID_field,
    output_points,
    GIStools,
    messages,
    quantile=0.2,
    smooth_level=600,
    uncertainty_sigma=300,
    uncertainty_factor=0.85,
    slope_sigma=300,
    slope_factor=2.0,
    smoothing=True,
    rdp_epsilon=0.02,
):
    if GIStools is None:
        raise ValueError("A GIStools package must be provided.")

    network = RiverNetworkTools.RiverNetwork()
    network.dict_attr_fields["id"] = RID_field
    network.dict_attr_fields["order"] = order_field

    reach_rows = list(GIStools.DataManagement.load_line_features(network_shp, [RID_field, order_field]))
    link_rows = list(
        GIStools.DataManagement.load_table_rows(
            links_table,
            [
                RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD,
                RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD,
            ],
        )
    )
    network.load_data(reach_rows, link_rows)

    for reach in network.reaches:
        try:
            reach.order = float(getattr(reach, "order", 0) or 0)
        except (TypeError, ValueError):
            reach.order = 0

    point_field_names = _unique_field_names(
        [
            id_field_pts,
            RID_field_pts,
            Distance_field_pts,
            dem_forws_field,
            DEM_ID_field,
        ]
    )
    points_info = GIStools.DataManagement.read_table_dataset(datapoints, point_field_names)

    collection = RiverNetworkTools.PointsCollection(network, "data")
    collection.dict_attr_fields["id"] = id_field_pts
    collection.dict_attr_fields["reach_id"] = RID_field_pts
    collection.dict_attr_fields["dist"] = Distance_field_pts
    collection.dict_attr_fields["z_forws"] = dem_forws_field
    collection.dict_attr_fields["DEM_ID"] = DEM_ID_field
    collection.load_table(points_info["records"])
    _initialize_cross_sections(collection)
    _run_processing(
        network,
        collection,
        messages,
        quantile=quantile,
        smooth_level=smooth_level,
        uncertainty_sigma=uncertainty_sigma,
        uncertainty_factor=uncertainty_factor,
        slope_sigma=slope_sigma,
        slope_factor=slope_factor,
        smoothing=smoothing,
        rdp_epsilon=rdp_epsilon,
    )

    if smoothing:
        collection.add_saved_variable("zws_smoothed", "float")
    collection.add_saved_variable("zws_quantilecarving", "float")

    output_rows = collection.save_points()
    _add_geometry_to_rows(output_rows, network, RID_field_pts, Distance_field_pts)

    extra_fields = [{"name": "zws_quantilecarving", "dtype": "float"}]
    if smoothing:
        extra_fields.insert(0, {"name": "zws_smoothed", "dtype": "float"})

    if output_points is None:
        return output_rows
    return GIStools.DataManagement.write_bed_assessment_points(
        output_points,
        output_rows,
        points_info,
        extra_fields,
        spatial_reference=GIStools.DataManagement.get_spatial_reference(network_shp),
    )


def ws_processing(
    data_points,
    pts_id,
    pts_rid,
    pts_dist,
    pts_ws,
    pts_dem,
    reaches,
    downstream,
    upstream,
    quantile=0.2,
    smoothing=True,
    smooth_level=600.0,
    uncertainty_sigma=300.0,
    uncertainty_factor=0.85,
    slope_sigma=300.0,
    slope_factor=2.0,
    feedback=None,
    rdp_epsilon=0.02,
):
    del upstream
    network = RiverNetworkTools.RiverNetwork()
    network.dict_attr_fields["id"] = "RID"
    network.dict_attr_fields["order"] = "order"
    reach_rows = []
    for rid, attributes in reaches.items():
        reach_rows.append(
            RiverNetworkTools.LineFeature(
                {"RID": rid, "order": attributes.get("order", 0)},
                [
                    RiverNetworkTools.Coordinate(0.0, float(rid)),
                    RiverNetworkTools.Coordinate(float(attributes.get("length", 0.0) or 0.0), float(rid)),
                ],
            )
        )
    link_rows = []
    for up_id, down_id in downstream.items():
        link_rows.append(
            {
                RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD: down_id,
                RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD: up_id,
            }
        )
    network.load_data(reach_rows, link_rows)
    for reach in network.reaches:
        try:
            reach.order = float(getattr(reach, "order", 0) or 0)
        except (TypeError, ValueError):
            reach.order = 0

    collection = RiverNetworkTools.PointsCollection(network, "data")
    collection.dict_attr_fields["id"] = pts_id
    collection.dict_attr_fields["reach_id"] = pts_rid
    collection.dict_attr_fields["dist"] = pts_dist
    collection.dict_attr_fields["z_forws"] = pts_ws
    collection.dict_attr_fields["DEM_ID"] = pts_dem
    collection.load_table(data_points)
    _initialize_cross_sections(collection)
    _run_processing(
        network,
        collection,
        _feedback_messages_adapter(feedback),
        quantile=quantile,
        smooth_level=smooth_level,
        uncertainty_sigma=uncertainty_sigma,
        uncertainty_factor=uncertainty_factor,
        slope_sigma=slope_sigma,
        slope_factor=slope_factor,
        smoothing=smoothing,
        rdp_epsilon=rdp_epsilon,
    )

    for row in data_points:
        cs = collection._points[int(row[pts_id])]
        row["z_forws"] = cs.z_forws
        row["zws_quantilecarving"] = cs.zws_quantilecarving
        row["zws_smoothed"] = cs.zws_smoothed
    return data_points


def _run_processing(
    network,
    collection,
    messages,
    quantile,
    smooth_level,
    uncertainty_sigma,
    uncertainty_factor,
    slope_sigma,
    slope_factor,
    smoothing,
    rdp_epsilon,
):
    list_cs = []
    prev_DEM_ID = None
    restartdown = False
    prev_cs = None
    prevcs_list = None

    for reach in network.browse_reaches_down_to_up(prioritize_reach_attribute="order"):
        if reach.is_downstream_end():
            prev_cs = None
            prevcs_list = None
        else:
            downstream_reach = reach.get_downstream_reach()
            if prev_cs is None or downstream_reach != prev_cs.reach:
                prev_cs = downstream_reach.get_last_point(collection)
                if restartdown:
                    prevcs_list = prev_cs
        isendreach = reach.is_upstream_end()
        endnode = reach.get_last_point(collection)
        for cs in reach.browse_points(collection):
            if prev_DEM_ID is not None and prev_DEM_ID != cs.DEM_ID:
                _process_dem_batch(
                    list_cs,
                    prevcs_list,
                    messages,
                    quantile,
                    rdp_epsilon,
                    smoothing,
                    smooth_level,
                    uncertainty_sigma,
                    uncertainty_factor,
                    slope_sigma,
                    slope_factor,
                )
                list_cs = []
                prevcs_list = None
                restartdown = False
            prev_DEM_ID = cs.DEM_ID
            list_cs.append(cs)

            if isendreach and cs == endnode:
                _process_dem_batch(
                    list_cs,
                    prevcs_list,
                    messages,
                    quantile,
                    rdp_epsilon,
                    smoothing,
                    smooth_level,
                    uncertainty_sigma,
                    uncertainty_factor,
                    slope_sigma,
                    slope_factor,
                )
                list_cs = []
                prev_DEM_ID = None
                restartdown = True
            prev_cs = cs


def _process_dem_batch(
    list_cs,
    prevcs_list,
    messages,
    quantile,
    rdp_epsilon,
    smoothing,
    smooth_level,
    uncertainty_sigma,
    uncertainty_factor,
    slope_sigma,
    slope_factor,
):
    if len(list_cs) == 0:
        return
    QuantileCarving(list_cs, prevcs_list, messages, tau=quantile)
    if rdp_epsilon is not None:
        rdp_simplify_and_resample(list_cs, epsilon=rdp_epsilon)
    if smoothing:
        Gaussian_weighted_moving_average(
            list_cs,
            prevcs_list,
            smooth_level,
            uncertainty_sigma,
            uncertainty_factor,
            slope_sigma,
            slope_factor,
        )


def _initialize_cross_sections(collection):
    for cs in collection._points.values():
        cs.z_forws = float(getattr(cs, "z_forws"))
        cs.zws_quantilecarving = cs.z_forws
        cs.zws_smoothed = cs.z_forws
        cs.ws_uncertainty = 0.0
        cs.restricted = 0.0
        cs.sd2 = 0.0
        cs.local_sigma = 0.0


def _build_continuous_distance_array(listcs):
    reachdist = 0.0
    distances = []
    lastreach = None
    for cs in listcs:
        if lastreach is not None and cs.reach != lastreach:
            reachdist += lastreach.length
        distances.append(cs.dist + reachdist)
        lastreach = cs.reach
    return np.array(distances, dtype=float)


def _rdp(points, epsilon):
    points = np.asarray(points, dtype=float)
    if len(points) <= 2:
        return points
    np.asarray(rdp(points, epsilon=epsilon), dtype=float)
    keep = np.zeros(len(points), dtype=bool)
    keep[0] = True
    keep[-1] = True
    _rdp_recursive(points, 0, len(points) - 1, float(epsilon), keep)
    return points[keep]


def _rdp_recursive(points, start_index, end_index, epsilon, keep):
    if end_index <= start_index + 1:
        return

    start_point = points[start_index]
    end_point = points[end_index]
    segment = end_point - start_point
    segment_length = np.hypot(segment[0], segment[1])

    max_distance = -1.0
    max_index = None
    for index in range(start_index + 1, end_index):
        point = points[index]
        if segment_length == 0:
            distance = np.hypot(*(point - start_point))
        else:
            relative = point - start_point
            distance = abs((segment[0] * relative[1]) - (segment[1] * relative[0])) / segment_length
        if distance > max_distance:
            max_distance = distance
            max_index = index

    if max_index is not None and max_distance > epsilon:
        keep[max_index] = True
        _rdp_recursive(points, start_index, max_index, epsilon, keep)
        _rdp_recursive(points, max_index, end_index, epsilon, keep)


def _add_geometry_to_rows(rows, rivernet, rid_field, dist_field):
    for row in rows:
        row["X"] = None
        row["Y"] = None
        try:
            reach = rivernet.get_reach(int(row[rid_field]))
            coordinate = reach.feature.interpolate(float(row[dist_field]))
        except Exception:
            continue
        row["X"] = coordinate.x
        row["Y"] = coordinate.y


def _unique_field_names(field_names):
    unique_names = []
    for field_name in field_names:
        if field_name not in unique_names:
            unique_names.append(field_name)
    return unique_names


def _add_warning(messages, message):
    if messages is not None:
        messages.add_warning(message)


class _FeedbackMessagesAdapter:
    def __init__(self, feedback):
        self.feedback = feedback

    def add_warning(self, message):
        if self.feedback is not None and hasattr(self.feedback, "pushWarning"):
            self.feedback.pushWarning(message)


def _feedback_messages_adapter(feedback):
    if feedback is None:
        return None
    return _FeedbackMessagesAdapter(feedback)
