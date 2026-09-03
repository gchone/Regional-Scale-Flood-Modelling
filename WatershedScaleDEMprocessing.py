from __future__ import annotations

import os

from CreateNetworkFromFC import execute_CreateNetworkFromFC
from FlowDirectionNetwork import execute_FlowDirectionNetwork
from OrderReaches import execute_OrderReaches


def execute_WatershedScaleDEMprocessing(
    DEM,
    streams_toburn,
    streamspoly_toburn,
    rivernet,
    rivernet_main,
    toburn_frompoly,
    toburn_fromlines,
    s_burned,
    s_fill,
    s_flow_dir,
    s_flow_acc,
    routes,
    routes_links,
    routes_main,
    routes_main_links,
    routeD8,
    linksD8,
    pathpointsD8,
    fd_net_relatetable,
    RID_field,
    DownEnd_field,
    Main_field,
    Qorder_field,
    messages=None,
    GIStools=None,
):
    if GIStools is None:
        GIStools = _autodetect_gistools()

    use_output_routes = not hasattr(GIStools.DataManagement, "update_line_attributes")
    main_routes_build_output = routes_main
    temp_cleanup_path = None
    routes_main_dataset = None
    routes_main_links_dataset = None
    routeD8_dataset = None
    linksD8_dataset = None
    pathpointsD8_dataset = None
    fd_net_relatetable_dataset = None
    if use_output_routes:
        main_routes_build_output, temp_cleanup_path = _build_temporary_output_path(routes_main, "_network_tmp")

    try:
        _add_message(messages, "Stream-burning DEM...")
        GIStools.Geoprocessing.rasterize_polygons_to_match(
            streamspoly_toburn,
            DEM,
            None,
            toburn_frompoly,
        )
        GIStools.Geoprocessing.rasterize_lines_to_match(
            streams_toburn,
            DEM,
            None,
            toburn_fromlines,
        )
        GIStools.Geoprocessing.burn_streams_into_dem(
            DEM,
            toburn_frompoly,
            toburn_fromlines,
            s_burned,
        )

        _add_message(messages, "Hydraulic processing of DEM...")
        GIStools.Geoprocessing.fill_dem(s_burned, s_fill)
        GIStools.Geoprocessing.compute_flow_direction(s_fill, s_flow_dir)
        GIStools.Geoprocessing.compute_flow_accumulation(s_flow_dir, s_flow_acc)

        _add_message(messages, "Identifying river networks...")
        execute_CreateNetworkFromFC(
            rivernet,
            routes,
            routes_links,
            RID_field,
            DownEnd_field,
            channeltype_field=Main_field,
            GIStools=GIStools,
            messages=messages,
        )
        execute_CreateNetworkFromFC(
            rivernet_main,
            main_routes_build_output,
            routes_main_links,
            RID_field,
            DownEnd_field,
            channeltype_field=None,
            GIStools=GIStools,
            messages=messages,
        )

        routes_main_dataset = _open_vector_dataset(GIStools, main_routes_build_output)
        routes_main_links_dataset = _open_vector_dataset(GIStools, routes_main_links)
        execute_FlowDirectionNetwork(
            routes_main_dataset,
            routes_main_links_dataset,
            RID_field,
            s_flow_dir,
            routeD8,
            linksD8,
            pathpointsD8,
            fd_net_relatetable,
            messages=messages,
            GIStools=GIStools,
        )

        routeD8_dataset = _open_vector_dataset(GIStools, routeD8)
        linksD8_dataset = _open_vector_dataset(GIStools, linksD8)
        pathpointsD8_dataset = _open_vector_dataset(GIStools, pathpointsD8)
        fd_net_relatetable_dataset = _open_vector_dataset(GIStools, fd_net_relatetable)
        if use_output_routes:
            execute_OrderReaches(
                routes_main_dataset,
                routes_main_links_dataset,
                RID_field,
                s_flow_acc,
                routeD8_dataset,
                linksD8_dataset,
                pathpointsD8_dataset,
                fd_net_relatetable_dataset,
                Qorder_field,
                messages=messages,
                GIStools=GIStools,
                output_routes=routes_main,
            )
        else:
            execute_OrderReaches(
                routes_main_dataset,
                routes_main_links_dataset,
                RID_field,
                s_flow_acc,
                routeD8_dataset,
                linksD8_dataset,
                pathpointsD8_dataset,
                fd_net_relatetable_dataset,
                Qorder_field,
                messages=messages,
                GIStools=GIStools,
            )
    finally:
        routes_main_dataset = None
        routes_main_links_dataset = None
        routeD8_dataset = None
        linksD8_dataset = None
        pathpointsD8_dataset = None
        fd_net_relatetable_dataset = None
        if temp_cleanup_path not in [None, ""]:
            GIStools.Geoprocessing.delete_dataset(temp_cleanup_path)

    return {
        "toburn_frompoly": toburn_frompoly,
        "toburn_fromlines": toburn_fromlines,
        "burned_dem": s_burned,
        "fill_dem": s_fill,
        "flow_direction": s_flow_dir,
        "flow_accumulation": s_flow_acc,
        "routes": routes,
        "routes_links": routes_links,
        "routes_main": routes_main,
        "routes_main_links": routes_main_links,
        "routeD8": routeD8,
        "linksD8": linksD8,
        "pathpointsD8": pathpointsD8,
        "fd_net_relatetable": fd_net_relatetable,
    }


def _build_temporary_output_path(output_path, suffix):
    output_path = str(output_path)
    if "|layername=" in output_path:
        dataset_path, layer_name = output_path.split("|layername=", 1)
    else:
        dataset_path = output_path
        layer_name = None

    root, extension = os.path.splitext(dataset_path)
    temporary_dataset = f"{root}{suffix}{extension}" if extension not in ["", ".gdb"] else f"{dataset_path}{suffix}"
    if layer_name not in [None, ""]:
        return temporary_dataset + "|layername=" + str(layer_name) + suffix, temporary_dataset
    return temporary_dataset, temporary_dataset


def _open_vector_dataset(GIStools, dataset, layer_name=None):
    opener = getattr(GIStools.DataManagement, "open_vector_dataset", None)
    if opener is None:
        return dataset
    return opener(dataset, layer_name)


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
    raise ValueError("A GIStools package must be provided.")


def _add_message(messages, message):
    if messages is not None:
        messages.add_message(message)
