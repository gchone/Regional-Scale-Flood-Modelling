import math

try:
    from scipy.optimize import minimize as _scipy_minimize
except Exception:
    _scipy_minimize = None

import RiverNetworkTools


G = 9.81
_SOLVER_FIELDS = [
    {"name": "solver", "dtype": "str", "max_length": 10},
    {"name": "y", "dtype": "float"},
    {"name": "R", "dtype": "float"},
    {"name": "v", "dtype": "float"},
    {"name": "z", "dtype": "float"},
    {"name": "h", "dtype": "float"},
    {"name": "s", "dtype": "float"},
    {"name": "Fr", "dtype": "float"},
]


class _OptimizationResult:
    def __init__(self, x=None, fun=None, success=True, message=""):
        self.x = [] if x is None else list(x)
        self.fun = fun
        self.success = success
        self.message = message


def execute_BedAssessment(
    route,
    route_RID_field,
    route_order_field,
    routelinks,
    points,
    points_IDfield,
    points_RIDfield,
    points_distfield,
    points_Qfield,
    points_Wfield,
    points_WSfield,
    points_DEMfield,
    manning,
    min_slope,
    output_pts,
    GIStools,
    messages,
    method="OVERSAMPLING",
    max_delta_y=None,
    resample=False,
):
    if GIStools is None:
        raise ValueError("A GIStools package must be provided.")

    method = str(method or "OVERSAMPLING").upper()
    if method not in ["SIMPLE", "OVERSAMPLING", "2-XS"]:
        _add_error(messages, "BedAssessment method must be one of SIMPLE, OVERSAMPLING or 2-XS.")

    rivernet = RiverNetworkTools.RiverNetwork()
    rivernet.dict_attr_fields["id"] = route_RID_field
    rivernet.dict_attr_fields["order"] = route_order_field

    reach_rows = list(GIStools.DataManagement.load_line_features(route, [route_RID_field, route_order_field]))
    link_rows = list(
        GIStools.DataManagement.load_table_rows(
            routelinks,
            [
                RiverNetworkTools.RiverNetwork.LINKS_DOWN_FIELD,
                RiverNetworkTools.RiverNetwork.LINKS_UP_FIELD,
            ],
        )
    )
    rivernet.load_data(reach_rows, link_rows)

    for reach in rivernet.reaches:
        try:
            reach.order = float(getattr(reach, "order", 0) or 0)
        except (TypeError, ValueError):
            reach.order = 0

    point_field_names = _unique_field_names(
        [
            points_IDfield,
            points_RIDfield,
            points_distfield,
            points_WSfield,
            points_Qfield,
            points_Wfield,
            points_DEMfield,
        ]
    )
    points_info = GIStools.DataManagement.read_table_dataset(points, point_field_names)

    points_coll = RiverNetworkTools.PointsCollection(rivernet, "data")
    points_coll.dict_attr_fields["id"] = points_IDfield
    points_coll.dict_attr_fields["reach_id"] = points_RIDfield
    points_coll.dict_attr_fields["dist"] = points_distfield
    points_coll.dict_attr_fields["wslidar"] = points_WSfield
    points_coll.dict_attr_fields["Q"] = points_Qfield
    points_coll.dict_attr_fields["width"] = points_Wfield
    points_coll.dict_attr_fields["DEM"] = points_DEMfield
    points_coll.load_table(points_info["records"])

    _initialize_cross_sections(points_coll)
    _prepare_solver_inputs(rivernet, points_coll, float(manning), float(min_slope))

    added_cs = []
    stopper = RiverNetworkTools.BrowsingStopper()
    done_reaches = []
    for reach in rivernet.browse_reaches_up_to_down(prioritize_reach_attribute="order", stopper=stopper):
        if reach.is_upstream_end():
            prev_cs = None
        if reach in done_reaches:
            stopper.break_generator = True
        else:
            for cs in reach.browse_points(points_coll, orientation="UP_TO_DOWN"):
                if prev_cs is None:
                    _manning_solver(cs)
                elif prev_cs.DEM != cs.DEM:
                    cs.s = prev_cs.s
                    _manning_solver(cs)
                else:
                    _recursive_inverse_1d_hydro(cs, prev_cs, float(min_slope), added_cs, messages, method, max_delta_y)
                prev_cs = cs
            done_reaches.append(reach)

    for field_definition in _SOLVER_FIELDS:
        points_coll.add_saved_variable(
            field_definition["name"],
            field_definition["dtype"],
            field_definition.get("max_length"),
        )

    if resample:
        _resample_points_to_original_resolution(rivernet, points_coll, added_cs)

    output_rows = points_coll.save_points()
    _add_geometry_to_rows(output_rows, rivernet, points_RIDfield, points_distfield)

    return GIStools.DataManagement.write_bed_assessment_points(
        output_pts,
        output_rows,
        points_info,
        _SOLVER_FIELDS,
        spatial_reference=GIStools.DataManagement.get_spatial_reference(route),
    )


def _initialize_cross_sections(points_coll):
    for cs in points_coll._points.values():
        cs.Q = _as_float(getattr(cs, "Q", None))
        cs.width = _as_float(getattr(cs, "width", None))
        cs.wslidar = _as_float(getattr(cs, "wslidar", None))
        cs.n = None
        cs.s = None
        cs.R = None
        cs.v = None
        cs.z = None
        cs.h = None
        cs.Fr = None
        cs.y = None
        cs.solver = None
        cs.listtosolve = []
        cs.position_in_list = 0
        cs.localdist_up = None
        cs.localdist_down = None
        cs.original_cs = cs
        cs.dist_to_original_cs = 0.0
        cs.nearby_cs = [cs]


def _prepare_solver_inputs(rivernet, points_coll, manning, min_slope):
    stopper = RiverNetworkTools.BrowsingStopper()
    done_reaches = []
    for reach in rivernet.browse_reaches_up_to_down(prioritize_reach_attribute="order", stopper=stopper):
        if reach.is_upstream_end():
            prev_cs = None
        if reach in done_reaches:
            stopper.break_generator = True
        else:
            for cs in reach.browse_points(points_coll, orientation="UP_TO_DOWN"):
                cs.listtosolve = []
                if prev_cs is not None:
                    cs.localdist_up = _distance_between_adjacent_sections(prev_cs, cs)
                    cs.listtosolve.append(prev_cs)
                cs.listtosolve.append(cs)
                cs.position_in_list = len(cs.listtosolve) - 1
                prev_cs = cs
            done_reaches.append(reach)

    for reach in rivernet.browse_reaches_down_to_up():
        if reach.is_downstream_end():
            prev_cs = None
        else:
            prev_cs = reach.get_downstream_reach().get_last_point(points_coll)
        lastpoint = reach.get_last_point(points_coll)
        for cs in reach.browse_points(points_coll):
            cs.n = manning
            cs.original_cs = cs
            cs.dist_to_original_cs = 0.0
            cs.nearby_cs = [cs]
            if prev_cs is not None:
                cs.localdist_down = _distance_between_adjacent_sections(cs, prev_cs)
                if reach.is_upstream_end() and cs == lastpoint:
                    if cs.localdist_down in [None, 0]:
                        cs.s = min_slope
                    else:
                        cs.s = max(min_slope, (cs.wslidar - prev_cs.wslidar) / cs.localdist_down)
                cs.listtosolve.append(prev_cs)
            elif reach.is_upstream_end() and cs == lastpoint:
                cs.s = min_slope
            prev_cs = cs


def _resample_points_to_original_resolution(rivernet, points_coll, added_cs):
    for reach in rivernet.browse_reaches_down_to_up():
        for cs in reach.browse_points(points_coll):
            if cs in added_cs:
                continue
            valid_nearby = [related_cs for related_cs in cs.nearby_cs if getattr(related_cs, "z", None) is not None]
            if len(valid_nearby) == 0:
                continue
            max_z_point = max(valid_nearby, key=lambda related_cs: related_cs.z)
            cs.z = max_z_point.z
            if len(cs.nearby_cs) > 1:
                cs.y = None
                cs.R = None
                cs.v = None
                cs.h = None
                cs.s = None
                cs.Fr = None
                cs.solver = "Resampled"

    for point in added_cs:
        points_coll.delete_point(point)


def _recursive_inverse_1d_hydro(cs, prev_cs, min_slope, added_cs, messages, method, max_delta_y):
    result = _direct_solver(cs, min_slope, method, max_delta_y)
    if not result.success:
        cs.solver = "error"
        _add_warning(
            messages,
            "Bed estimation failed at reach ID {} dist {:.2f}m: {}".format(
                cs.reach.id,
                cs.dist,
                result.message or "unknown solver failure",
            ),
        )

    localdist = cs.localdist_up
    if (
        method == "OVERSAMPLING"
        and prev_cs.Fr not in [None, 0]
        and cs.Fr is not None
        and localdist not in [None, 0]
        and abs(cs.Fr - prev_cs.Fr) / abs(prev_cs.Fr) > 0.5
        and localdist > 0.1
    ):
        if cs.reach == prev_cs.reach:
            newcs = cs.reach.add_point((cs.dist + prev_cs.dist) / 2.0, cs.points_collection)
        else:
            if localdist / 2.0 < prev_cs.dist:
                newcs = prev_cs.reach.add_point(localdist / 2.0, cs.points_collection)
            else:
                newcs = cs.reach.add_point(cs.dist + localdist / 2.0, cs.points_collection)

        _initialize_added_cross_section(newcs)
        for attribute_name in ["width", "Q", "wslidar"]:
            upstream_value = getattr(prev_cs, attribute_name, None)
            downstream_value = getattr(cs, attribute_name, None)
            if upstream_value is None or downstream_value is None:
                setattr(newcs, attribute_name, None)
                continue
            slope = (downstream_value - upstream_value) / (0 - localdist)
            setattr(newcs, attribute_name, slope * (localdist / 2.0) + downstream_value)

        newcs.n = cs.n
        newcs.DEM = prev_cs.DEM
        newcs.solver = "regular"

        newcs.listtosolve = [prev_cs, newcs]
        newcs.position_in_list = 1
        cs.listtosolve = [newcs, cs]
        cs.position_in_list = 1

        cs.localdist_up = localdist / 2.0
        newcs.localdist_up = localdist / 2.0
        newcs.localdist_down = localdist / 2.0
        prev_cs.localdist_down = localdist / 2.0
        newcs.listtosolve = [prev_cs, newcs, cs]
        if len(prev_cs.listtosolve) != 0:
            prev_cs.listtosolve[-1] = newcs
        newcs.position_in_list = 1

        if prev_cs.dist_to_original_cs + newcs.localdist_up < cs.dist_to_original_cs + newcs.localdist_down:
            newcs.dist_to_original_cs = prev_cs.dist_to_original_cs + newcs.localdist_up
            newcs.original_cs = prev_cs.original_cs
        else:
            newcs.dist_to_original_cs = cs.dist_to_original_cs + newcs.localdist_down
            newcs.original_cs = cs.original_cs
        newcs.original_cs.nearby_cs.append(newcs)
        added_cs.append(newcs)

        _recursive_inverse_1d_hydro(newcs, prev_cs, min_slope, added_cs, messages, method, max_delta_y)
        _recursive_inverse_1d_hydro(cs, newcs, min_slope, added_cs, messages, method, max_delta_y)


def _initialize_added_cross_section(cs):
    cs.n = None
    cs.s = None
    cs.R = None
    cs.v = None
    cs.z = None
    cs.h = None
    cs.Fr = None
    cs.y = None
    cs.solver = None
    cs.dist_to_original_cs = 0.0
    cs.original_cs = cs
    cs.nearby_cs = [cs]


def _manning_solver(cs):
    if not _has_valid_hydraulic_inputs(cs) or cs.s is None or cs.s <= 0:
        _clear_solution(cs, "error")
        return _OptimizationResult(success=False, message="invalid Manning inputs")

    def equation(y_value):
        hydraulic_radius = (cs.width * y_value) / (cs.width + 2 * y_value)
        return (y_value * cs.width * hydraulic_radius ** (2.0 / 3.0) * cs.s ** 0.5) / cs.n - cs.Q

    try:
        cs.y = _solve_positive_root(equation)
    except ValueError as exc:
        _clear_solution(cs, "error")
        return _OptimizationResult(success=False, message=str(exc))

    cs.R = (cs.width * cs.y) / (cs.width + 2 * cs.y)
    cs.ycrit = (cs.Q / (cs.width * G ** 0.5)) ** (2.0 / 3.0)
    cs.v = cs.Q / (cs.width * cs.y)
    cs.z = cs.wslidar - cs.y
    cs.h = cs.wslidar + cs.v ** 2 / (2 * G)
    cs.Fr = cs.v / (G * cs.y) ** 0.5
    cs.solver = "manning"
    return _OptimizationResult(x=[cs.y], fun=0.0)


def _direct_solver(cs, min_slope, method, max_delta_y):
    if len(cs.listtosolve) == 0:
        _clear_solution(cs, "error")
        return _OptimizationResult(success=False, message="missing cross-section context")

    if method != "2-XS" and len(cs.listtosolve) == 3:
        cs.listtosolve.pop(2)

    dimension = len(cs.listtosolve) - 1
    if dimension <= 0:
        _clear_solution(cs, "error")
        return _OptimizationResult(success=False, message="missing upstream reference")

    if not _has_valid_hydraulic_inputs(cs):
        _clear_solution(cs, "error")
        return _OptimizationResult(success=False, message="invalid channel geometry or discharge")

    for index in range(dimension):
        cs_down = cs.listtosolve[index + 1]
        if not _has_valid_hydraulic_inputs(cs_down):
            _clear_solution(cs, "error")
            return _OptimizationResult(success=False, message="invalid hydraulic inputs in cross-section list")
        cs_down.ycrit = (cs_down.Q / (cs_down.width * G ** 0.5)) ** (2.0 / 3.0)

    ycrit = [cs.listtosolve[index + 1].ycrit for index in range(dimension)]
    if max_delta_y is not None:
        upper_bound = max(
            cs.listtosolve[1].ycrit,
            min(
                cs.listtosolve[0].y * (1 + float(max_delta_y) * cs.localdist_up / 100.0),
                cs.listtosolve[1].width,
            ),
        )
    else:
        upper_bound = max(cs.listtosolve[1].ycrit, cs.listtosolve[1].width)
    max_y = [upper_bound]
    max_y.extend([cs.listtosolve[index + 1].width for index in range(1, dimension)])
    bounds = []
    for index in range(dimension):
        lower = max(ycrit[index], 1e-9)
        upper = max(max_y[index], lower + 1e-9)
        bounds.append((lower, upper))

    def equations(y_values):
        values = _normalize_solution_vector(y_values, dimension)
        dif_energy = []
        for index in range(dimension):
            cs_tosolve = cs.listtosolve[index + 1]
            cs_ref = cs.listtosolve[index]
            localdist = cs_tosolve.localdist_up
            if localdist is None or localdist <= 0:
                return float("inf")
            if index == 0:
                if cs_ref.h is None or cs_ref.s is None:
                    return float("inf")
                cs_ref.temp_h = cs_ref.h
                cs_ref.temp_s = cs_ref.s
            if abs(cs_ref.wslidar - cs_tosolve.wslidar) / localdist <= min_slope:
                cs_tosolve.solver = "min_slope"
                h_ref = cs_ref.temp_h + localdist * (
                    min_slope - (cs_ref.wslidar - cs_tosolve.wslidar) / localdist
                )
            else:
                h_ref = cs_ref.temp_h

            y_value = values[index]
            if y_value <= 0:
                return float("inf")
            v_value = cs_tosolve.Q / (cs_tosolve.width * y_value)
            hydraulic_radius = (cs_tosolve.width * y_value) / (cs_tosolve.width + 2 * y_value)
            if hydraulic_radius <= 0:
                return float("inf")
            slope_value = (cs_tosolve.n ** 2 * v_value ** 2) / (hydraulic_radius ** (4.0 / 3.0))
            head_value = cs_tosolve.wslidar + v_value ** 2 / (2 * G)
            cs_tosolve.temp_h = head_value
            cs_tosolve.temp_s = slope_value
            friction_head = localdist * (slope_value + cs_ref.temp_s) / 2.0
            if dimension == 1:
                friction_head = localdist * slope_value
            dif_energy.append(abs(friction_head + head_value - h_ref))
        return math.sqrt(sum(value ** 2 for value in dif_energy))

    res = _minimize_with_bounds(equations, ycrit, bounds)
    cs.solver = "regular"

    result_index = max(0, cs.position_in_list - 1)
    gradient_limit = bounds[result_index][1]
    if max_delta_y is not None and res.x[result_index] >= gradient_limit - 1e-6:
        cs.solver = "max depth gradient"
    if res.x[result_index] >= cs.listtosolve[1].width - 1e-6:
        cs.solver = "max depth"

    supercritical_bounds = [(1e-9, max(limit, 1e-9)) for limit in ycrit]
    res_super = _minimize_with_bounds(equations, ycrit, supercritical_bounds)
    if res_super.fun is not None and (res.fun is None or res_super.fun < res.fun):
        res = res_super

    cs.y = res.x[result_index]
    if cs.y < cs.ycrit:
        cs.y = cs.ycrit
        cs.solver = "critical"

    cs.R = (cs.width * cs.y) / (cs.width + 2 * cs.y)
    cs.v = cs.Q / (cs.width * cs.y)
    cs.z = cs.wslidar - cs.y
    cs.s = (cs.n ** 2 * cs.v ** 2) / (cs.R ** (4.0 / 3.0))
    cs.h = cs.wslidar + cs.v ** 2 / (2 * G)
    cs.Fr = cs.v / (G * cs.y) ** 0.5
    return res


def _minimize_with_bounds(objective, initial_guess, bounds):
    if len(bounds) == 1:
        lower, upper = bounds[0]
        return _bounded_minimize_scalar(lambda candidate: objective([candidate]), lower, upper)

    if _scipy_minimize is None:
        best = list(initial_guess)
        best_fun = objective(best)
        for _ in range(12):
            improved = False
            for index, (lower, upper) in enumerate(bounds):
                def one_dim(candidate):
                    current = list(best)
                    current[index] = candidate
                    return objective(current)

                local = _bounded_minimize_scalar(one_dim, lower, upper)
                if local.fun < best_fun:
                    best[index] = local.x[0]
                    best_fun = local.fun
                    improved = True
            if not improved:
                break
        return _OptimizationResult(x=best, fun=best_fun)

    result = _scipy_minimize(
        objective,
        initial_guess,
        method="Nelder-Mead",
        bounds=bounds,
        options={"xatol": 1e-3, "fatol": 1e-6},
    )
    return _OptimizationResult(
        x=getattr(result, "x", initial_guess),
        fun=getattr(result, "fun", None),
        success=bool(getattr(result, "success", False)),
        message=str(getattr(result, "message", "")),
    )


def _bounded_minimize_scalar(objective, lower, upper, tolerance=1e-4, max_iter=128):
    phi = (1 + 5 ** 0.5) / 2.0
    inverse_phi = 1 / phi
    a = float(lower)
    b = float(upper)
    if not math.isfinite(a) or not math.isfinite(b) or b <= a:
        midpoint = max(a, b)
        return _OptimizationResult(x=[midpoint], fun=objective(midpoint))

    c = b - (b - a) * inverse_phi
    d = a + (b - a) * inverse_phi
    fc = objective(c)
    fd = objective(d)

    for _ in range(max_iter):
        if abs(b - a) <= tolerance:
            break
        if fc < fd:
            b = d
            d = c
            fd = fc
            c = b - (b - a) * inverse_phi
            fc = objective(c)
        else:
            a = c
            c = d
            fc = fd
            d = a + (b - a) * inverse_phi
            fd = objective(d)

    x_value = c if fc <= fd else d
    return _OptimizationResult(x=[x_value], fun=min(fc, fd))


def _solve_positive_root(function, lower=1e-6, upper=1.0, max_iter=80):
    lower_value = function(lower)
    upper_value = function(upper)
    attempts = 0
    while upper_value < 0 and attempts < 60:
        upper *= 2.0
        upper_value = function(upper)
        attempts += 1
    if lower_value == 0:
        return lower
    if upper_value == 0:
        return upper
    if lower_value > 0 or upper_value < 0:
        raise ValueError("Unable to bracket a Manning solution.")

    for _ in range(max_iter):
        midpoint = (lower + upper) / 2.0
        midpoint_value = function(midpoint)
        if abs(midpoint_value) < 1e-8:
            return midpoint
        if midpoint_value > 0:
            upper = midpoint
        else:
            lower = midpoint
    return (lower + upper) / 2.0


def _normalize_solution_vector(values, dimension):
    try:
        result = [float(value) for value in values]
    except TypeError:
        result = [float(values)]
    if len(result) < dimension:
        result.extend([result[-1]] * (dimension - len(result)))
    return result


def _distance_between_adjacent_sections(upstream_cs, downstream_cs):
    if upstream_cs.reach == downstream_cs.reach:
        return upstream_cs.dist - downstream_cs.dist
    return downstream_cs.reach.length - downstream_cs.dist + upstream_cs.dist


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


def _has_valid_hydraulic_inputs(cs):
    return (
        cs.Q is not None
        and cs.Q > 0
        and cs.width is not None
        and cs.width > 0
        and cs.n is not None
        and cs.n > 0
        and cs.wslidar is not None
    )


def _clear_solution(cs, solver_name):
    cs.y = None
    cs.R = None
    cs.v = None
    cs.z = None
    cs.h = None
    cs.s = None
    cs.Fr = None
    cs.solver = solver_name


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unique_field_names(field_names):
    unique_names = []
    for field_name in field_names:
        if field_name not in unique_names:
            unique_names.append(field_name)
    return unique_names


def _add_warning(messages, message):
    if messages is not None:
        messages.add_warning(message)


def _add_error(messages, message):
    if messages is not None:
        messages.add_error(message)
    raise ValueError(message)
