import math
import os

import numpy as np
from qgis.core import QgsFeatureRequest, QgsGeometry, QgsSpatialIndex, QgsVectorLayer
import processing

# Create a buffer around a shape
def buffer(input_shapefile, output_shapefile, buffer_distance):
    processing.run("native:buffer", {
        'INPUT': input_shapefile,
        'DISTANCE': buffer_distance,
        'OUTPUT': output_shapefile
    })

# Add other geoprocessing tools and procedures
# ...


def create_points_on_route_layer(routes, routes_id_field, points_onroute, points_onroute_ridfield, points_onroute_distfield):
    return points_onroute


def delete_layer(layer_name):
    return


def _rasterize_vector_to_match(input_vector, reference_raster, reference_grid, output_path):
    if reference_grid is None:
        from osgeo import gdal

        reference_path = _resolve_raster_path(reference_raster)
        reference_dataset = gdal.Open(reference_path, gdal.GA_ReadOnly)
        if reference_dataset is None:
            raise ValueError(f"GDAL could not open reference raster: {reference_path}")
        transform = reference_dataset.GetGeoTransform()
        pixel_width = abs(transform[1])
        pixel_height = abs(transform[5])
        y_max = transform[3]
        y_min = y_max - reference_dataset.RasterYSize * pixel_height
        reference_grid = {
            "x_min": float(transform[0]),
            "y_min": float(y_min),
            "y_max": float(y_max),
            "width": int(reference_dataset.RasterXSize),
            "height": int(reference_dataset.RasterYSize),
            "pixel_width": float(pixel_width),
            "pixel_height": float(pixel_height),
        }
        reference_dataset = None
    processing.run("gdal:rasterize", {
        "INPUT": input_vector,
        "FIELD": "",
        "BURN": 1,
        "USE_Z": False,
        "UNITS": 1,
        "WIDTH": float(reference_grid["pixel_width"]),
        "HEIGHT": float(reference_grid["pixel_height"]),
        "EXTENT": (
            f"{reference_grid['x_min']},"
            f"{reference_grid['x_min'] + reference_grid['width'] * reference_grid['pixel_width']},"
            f"{reference_grid['y_min']},"
            f"{reference_grid['y_max']} "
            f"[{reference_raster.crs().authid()}]"
        ),
        "NODATA": float(-255),
        "OPTIONS": "",
        "DATA_TYPE": 5,
        "INIT": float(-255),
        "INVERT": False,
        "EXTRA": "-tap",
        "OUTPUT": output_path,
    })
    return output_path


def rasterize_polygons_to_match(input_polygons, reference_raster, reference_grid, output_path):
    return _rasterize_vector_to_match(input_polygons, reference_raster, reference_grid, output_path)


def rasterize_lines_to_match(input_lines, reference_raster, reference_grid, output_path):
    return _rasterize_vector_to_match(input_lines, reference_raster, reference_grid, output_path)


def point_to_raster_most_frequent(input_points, value_field, reference_raster, output_path):
    from osgeo import gdal
    from . import DataManagement

    point_layer = input_points if hasattr(input_points, "getFeatures") else DataManagement.open_vector_dataset(input_points)
    reference_path = _resolve_raster_path(reference_raster)
    reference_dataset = gdal.Open(reference_path, gdal.GA_ReadOnly)
    if reference_dataset is None:
        raise ValueError(f"GDAL could not open reference raster: {reference_path}")

    band = reference_dataset.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    transform = reference_dataset.GetGeoTransform()
    projection = reference_dataset.GetProjection()
    width = int(reference_dataset.RasterXSize)
    height = int(reference_dataset.RasterYSize)
    pixel_width = abs(float(transform[1]))
    pixel_height = abs(float(transform[5]))
    x_min = float(transform[0])
    y_max = float(transform[3])
    y_min = y_max - height * pixel_height
    output_nodata = np.nan if nodata is None else float(nodata)
    cell_values = {}

    for feature_index, feature in enumerate(point_layer.getFeatures()):
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue
        point = geometry.asPoint()
        x_value = float(point.x())
        y_value = float(point.y())
        if x_value < x_min or x_value >= x_min + width * pixel_width:
            continue
        if y_value > y_max or y_value < y_min:
            continue

        column = int((x_value - x_min) / pixel_width)
        row = int((y_max - y_value) / pixel_height)
        if row == height and abs(y_value - y_min) <= 1e-9:
            row = height - 1
        if column < 0 or row < 0 or column >= width or row >= height:
            continue

        raw_value = feature[value_field]
        if raw_value in [None, ""]:
            continue
        try:
            raster_value = float(raw_value)
        except (TypeError, ValueError):
            raise ValueError(f"Field '{value_field}' must contain numeric values.")
        if np.isnan(raster_value):
            continue

        cell_key = (row, column)
        if cell_key not in cell_values:
            cell_values[cell_key] = {"counts": {}, "first_seen": {}}
        counts = cell_values[cell_key]["counts"]
        first_seen = cell_values[cell_key]["first_seen"]
        counts[raster_value] = counts.get(raster_value, 0) + 1
        if raster_value not in first_seen:
            first_seen[raster_value] = feature_index

    output_array = np.full((height, width), output_nodata, dtype=np.float32)
    for (row, column), summary in cell_values.items():
        value = min(
            summary["counts"].items(),
            key=lambda item: (-item[1], summary["first_seen"][item[0]]),
        )[0]
        output_array[row, column] = float(value)

    reference_dataset = None
    _delete_qgis_dataset(output_path)
    output_dataset = gdal.GetDriverByName("GTiff").Create(str(output_path), width, height, 1, gdal.GDT_Float32)
    if output_dataset is None:
        raise ValueError(f"GDAL could not create raster: {output_path}")
    output_dataset.SetGeoTransform(transform)
    if projection not in [None, ""]:
        output_dataset.SetProjection(projection)
    output_band = output_dataset.GetRasterBand(1)
    output_band.SetNoDataValue(output_nodata)
    output_band.WriteArray(output_array)
    output_band.FlushCache()
    output_dataset.FlushCache()
    output_dataset = None
    return output_path


def build_tiling_buffer_extents(segments_raster, buffer_distance, output_folder):
    line_segments = os.path.join(output_folder, "line_segments.gpkg")
    buffered_segments = os.path.join(output_folder, "buff_segments.gpkg")

    temp_seg_poly = os.path.join(output_folder, "_tmp_seg_poly.gpkg")
    temp_seg_poly_dissolved = os.path.join(output_folder, "_tmp_seg_poly_dissolved.gpkg")
    temp_regions = os.path.join(output_folder, "_tmp_regions.tif")
    temp_euc_poly = os.path.join(output_folder, "_tmp_euc_poly.gpkg")
    temp_line_buffer = os.path.join(output_folder, "_tmp_linebuf.gpkg")
    temp_merged = os.path.join(output_folder, "_tmp_merged.gpkg")
    temp_buffered_dissolved = os.path.join(output_folder, "_tmp_buffered_dissolved.gpkg")

    for path in [
        line_segments,
        buffered_segments,
        temp_seg_poly,
        temp_seg_poly_dissolved,
        temp_regions,
        temp_euc_poly,
        temp_line_buffer,
        temp_merged,
        temp_buffered_dissolved,
    ]:
        _delete_qgis_dataset(path)

    processing.run("gdal:polygonize", {
        "INPUT": segments_raster,
        "BAND": 1,
        "FIELD": "GRID_CODE",
        "EIGHT_CONNECTEDNESS": False,
        "EXTRA": "",
        "OUTPUT": temp_seg_poly,
    })
    processing.run("native:dissolve", {
        "INPUT": temp_seg_poly,
        "FIELD": ["GRID_CODE"],
        "OUTPUT": temp_seg_poly_dissolved,
    })
    processing.run("native:polygonstolines", {
        "INPUT": temp_seg_poly_dissolved,
        "OUTPUT": line_segments,
    })

    processing.run("grass:r.grow", {
        "input": segments_raster,
        "radius": buffer_distance,
        "metric": 0,
        "-m": True,
        "output": temp_regions,
        "GRASS_REGION_PARAMETER": None,
        "GRASS_REGION_CELLSIZE_PARAMETER": 0,
        "GRASS_RASTER_FORMAT_OPT": "",
        "GRASS_RASTER_FORMAT_META": "",
    })
    processing.run("gdal:polygonize", {
        "INPUT": temp_regions,
        "BAND": 1,
        "FIELD": "GRID_CODE",
        "EIGHT_CONNECTEDNESS": False,
        "EXTRA": "",
        "OUTPUT": temp_euc_poly,
    })

    processing.run("native:buffer", {
        "INPUT": line_segments,
        "DISTANCE": float(buffer_distance) / 10.0,
        "SEGMENTS": 5,
        "END_CAP_STYLE": 0,
        "JOIN_STYLE": 0,
        "MITER_LIMIT": 2,
        "DISSOLVE": False,
        "OUTPUT": temp_line_buffer,
    })
    processing.run("native:mergevectorlayers", {
        "LAYERS": [temp_line_buffer, temp_euc_poly],
        "CRS": None,
        "OUTPUT": temp_merged,
    })
    processing.run("native:dissolve", {
        "INPUT": temp_merged,
        "FIELD": ["GRID_CODE"],
        "OUTPUT": temp_buffered_dissolved,
    })
    processing.run("native:multiparttosingleparts", {
        "INPUT": temp_buffered_dissolved,
        "OUTPUT": buffered_segments,
    })

    buffered_layer = QgsVectorLayer(buffered_segments, "buffered_segments", "ogr")
    records = []
    for feature in buffered_layer.getFeatures():
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue
        bbox = geometry.boundingBox()
        records.append({
            "GRID_CODE": int(feature["GRID_CODE"]),
            "XMin": float(bbox.xMinimum()),
            "YMin": float(bbox.yMinimum()),
            "XMax": float(bbox.xMaximum()),
            "YMax": float(bbox.yMaximum()),
        })

    for path in [
        temp_seg_poly,
        temp_seg_poly_dissolved,
        temp_regions,
        temp_euc_poly,
        temp_line_buffer,
        temp_merged,
        temp_buffered_dissolved,
    ]:
        _delete_qgis_dataset(path)

    return {
        "line_segments": line_segments,
        "buffered_segments": buffered_segments,
        "records": records,
    }


def _delete_qgis_dataset(path):
    candidates = [path]
    root, extension = os.path.splitext(path)
    if extension.lower() == ".shp":
        candidates.extend([root + ".dbf", root + ".shx", root + ".prj", root + ".cpg", root + ".qmd"])
    for candidate in candidates:
        if os.path.exists(candidate):
            try:
                os.remove(candidate)
            except OSError:
                pass


def clip_raster_to_extent(input_raster, extent, output_path):
    from osgeo import gdal
    import math

    input_path = _resolve_raster_path(input_raster)
    dataset = gdal.Open(input_path, gdal.GA_ReadOnly)
    if dataset is None:
        raise ValueError(f"GDAL could not open raster: {input_path}")

    transform = dataset.GetGeoTransform()
    x_res = abs(transform[1])
    y_res = abs(transform[5])
    nodata = dataset.GetRasterBand(1).GetNoDataValue()
    dataset = None

    xmin, ymin, xmax, ymax = extent
    origin_x = transform[0]
    origin_y = transform[3]
    snapped_extent = (
        origin_x + math.floor((float(xmin) - origin_x) / x_res) * x_res,
        origin_y - math.ceil((origin_y - float(ymin)) / y_res) * y_res,
        origin_x + math.ceil((float(xmax) - origin_x) / x_res) * x_res,
        origin_y - math.floor((origin_y - float(ymax)) / y_res) * y_res,
    )

    _delete_qgis_dataset(output_path)
    warp_kwargs = {
        "outputBounds": snapped_extent,
        "xRes": x_res,
        "yRes": y_res,
        "format": "GTiff",
    }
    if nodata is not None:
        warp_kwargs["dstNodata"] = nodata
    result = gdal.Warp(output_path, input_path, **warp_kwargs)
    if result is None:
        raise ValueError(f"GDAL could not clip raster to extent: {output_path}")
    result = None
    return output_path


def clip_raster_to_template(input_raster, template_raster, output_path):
    from osgeo import gdal

    input_path = _resolve_raster_path(input_raster)
    template_path = _resolve_raster_path(template_raster)
    source_dataset = gdal.Open(input_path, gdal.GA_ReadOnly)
    if source_dataset is None:
        raise ValueError(f"GDAL could not open raster: {input_path}")
    nodata = source_dataset.GetRasterBand(1).GetNoDataValue()
    source_dataset = None

    template_dataset = gdal.Open(template_path, gdal.GA_ReadOnly)
    if template_dataset is None:
        raise ValueError(f"GDAL could not open template raster: {template_path}")
    transform = template_dataset.GetGeoTransform()
    projection = template_dataset.GetProjection()
    x_res = abs(transform[1])
    y_res = abs(transform[5])
    width = int(template_dataset.RasterXSize)
    height = int(template_dataset.RasterYSize)
    xmin = float(transform[0])
    ymax = float(transform[3])
    xmax = xmin + width * x_res
    ymin = ymax - height * y_res
    template_dataset = None

    _delete_qgis_dataset(output_path)
    warp_kwargs = {
        "outputBounds": (xmin, ymin, xmax, ymax),
        "width": width,
        "height": height,
        "dstSRS": projection,
        "format": "GTiff",
        "resampleAlg": gdal.GRA_NearestNeighbour,
    }
    if nodata is not None:
        warp_kwargs["dstNodata"] = nodata
    result = gdal.Warp(output_path, input_path, **warp_kwargs)
    if result is None:
        raise ValueError(f"GDAL could not clip raster to template: {output_path}")
    result = None
    return output_path


def raster_to_ascii(input_raster, output_path):
    from osgeo import gdal

    input_path = _resolve_raster_path(input_raster)
    _delete_qgis_dataset(output_path)
    result = gdal.Translate(output_path, input_path, format="AAIGrid")
    if result is None:
        raise ValueError(f"GDAL could not convert raster to ASCII: {output_path}")
    result = None
    return output_path


def _resolve_raster_path(raster):
    return raster.source() if hasattr(raster, "source") else str(raster)


def delete_dataset(path):
    if path in [None, ""]:
        return
    _delete_qgis_dataset(str(path))


def rasterize_polygons_with_boundaries(input_polygons, reference_raster, reference_grid, output_path):
    from osgeo import gdal, ogr, osr

    nodata_value = -1
    width = int(reference_grid["width"])
    height = int(reference_grid["height"])
    transform = (
        float(reference_grid["x_min"]),
        float(reference_grid["pixel_width"]),
        0.0,
        float(reference_grid["y_max"]),
        0.0,
        -float(reference_grid["pixel_height"]),
    )
    projection = reference_grid.get("projection")

    def _new_mem_layer(layer_name, geometry_type):
        memory_ds = ogr.GetDriverByName("Memory").CreateDataSource(layer_name)
        spatial_ref = osr.SpatialReference()
        if projection not in [None, ""]:
            spatial_ref.ImportFromWkt(projection)
        layer = memory_ds.CreateLayer(layer_name, srs=spatial_ref, geom_type=geometry_type)
        layer.CreateField(ogr.FieldDefn("ZONE_ID", ogr.OFTInteger))
        return memory_ds, layer

    poly_ds, poly_layer = _new_mem_layer("polygons", ogr.wkbPolygon)
    line_ds, line_layer = _new_mem_layer("boundaries", ogr.wkbLineString)

    for feature in input_polygons.getFeatures():
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue
        zone_id = int(feature.id())
        ogr_geometry = ogr.CreateGeometryFromWkt(geometry.asWkt())

        poly_feature = ogr.Feature(poly_layer.GetLayerDefn())
        poly_feature.SetField("ZONE_ID", zone_id)
        poly_feature.SetGeometry(ogr_geometry.Clone())
        poly_layer.CreateFeature(poly_feature)

        boundary_geometry = ogr_geometry.Boundary()
        if boundary_geometry is None:
            continue
        if boundary_geometry.GetGeometryType() in [ogr.wkbLineString, ogr.wkbLineString25D]:
            line_geometries = [boundary_geometry]
        else:
            line_geometries = [boundary_geometry.GetGeometryRef(i).Clone() for i in range(boundary_geometry.GetGeometryCount())]
        for line_geometry in line_geometries:
            line_feature = ogr.Feature(line_layer.GetLayerDefn())
            line_feature.SetField("ZONE_ID", zone_id)
            line_feature.SetGeometry(line_geometry)
            line_layer.CreateFeature(line_feature)

    driver = gdal.GetDriverByName("MEM")
    polygon_raster = driver.Create("", width, height, 1, gdal.GDT_Int32)
    line_raster = driver.Create("", width, height, 1, gdal.GDT_Int32)
    for dataset in [polygon_raster, line_raster]:
        dataset.SetGeoTransform(transform)
        if projection not in [None, ""]:
            dataset.SetProjection(projection)
        dataset.GetRasterBand(1).Fill(nodata_value)
        dataset.GetRasterBand(1).SetNoDataValue(nodata_value)

    gdal.RasterizeLayer(polygon_raster, [1], poly_layer, options=["ATTRIBUTE=ZONE_ID"])
    gdal.RasterizeLayer(line_raster, [1], line_layer, options=["ATTRIBUTE=ZONE_ID"])

    polygon_array = polygon_raster.GetRasterBand(1).ReadAsArray()
    line_array = line_raster.GetRasterBand(1).ReadAsArray()
    combined_array = np.where(polygon_array != nodata_value, polygon_array, line_array).astype(np.int32)

    _delete_qgis_dataset(output_path)
    output_dataset = gdal.GetDriverByName("GTiff").Create(str(output_path), width, height, 1, gdal.GDT_Int32)
    output_dataset.SetGeoTransform(transform)
    if projection not in [None, ""]:
        output_dataset.SetProjection(projection)
    band = output_dataset.GetRasterBand(1)
    band.SetNoDataValue(nodata_value)
    band.WriteArray(combined_array)
    band.FlushCache()
    output_dataset.FlushCache()

    output_dataset = None
    polygon_raster = None
    line_raster = None
    poly_ds = None
    line_ds = None
    return output_path


def clip_raster_to_feature(input_raster, feature_source, feature_oid, output_path):
    from osgeo import gdal

    input_path = _resolve_raster_path(input_raster)
    feature_request = QgsFeatureRequest(int(feature_oid))
    feature = None
    for item in feature_source.getFeatures(feature_request):
        feature = item
        break
    if feature is None or feature.geometry() is None or feature.geometry().isEmpty():
        raise ValueError(f"Could not load feature {feature_oid} for clipping.")

    source_dataset = gdal.Open(input_path, gdal.GA_ReadOnly)
    if source_dataset is None:
        raise ValueError(f"GDAL could not open raster: {input_path}")
    band = source_dataset.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    transform = source_dataset.GetGeoTransform()
    x_res = abs(transform[1])
    y_res = abs(transform[5])
    source_dataset = None

    _delete_qgis_dataset(output_path)
    warp_result = gdal.Warp(
        str(output_path),
        input_path,
        format="GTiff",
        cutlineWKT=feature.geometry().asWkt(),
        cropToCutline=True,
        xRes=x_res,
        yRes=y_res,
        srcNodata=nodata,
        dstNodata=nodata,
        targetAlignedPixels=True,
        outputType=gdal.GDT_Float32,
    )
    if warp_result is None:
        raise ValueError(f"GDAL could not clip raster to feature: {feature_oid}")
    warp_result = None
    return output_path


def collect_intersection_start_points(routes_main, polygon_feature_class, polygon_oid):
    feature_request = QgsFeatureRequest(int(polygon_oid))
    polygon_feature = None
    for item in polygon_feature_class.getFeatures(feature_request):
        polygon_feature = item
        break
    if polygon_feature is None or polygon_feature.geometry() is None or polygon_feature.geometry().isEmpty():
        raise ValueError(f"Could not load feature {polygon_oid} for route intersections.")

    polygon_geometry = polygon_feature.geometry()
    points = []

    for route_feature in routes_main.getFeatures():
        route_geometry = route_feature.geometry()
        if route_geometry is None or route_geometry.isEmpty():
            continue
        if not route_geometry.intersects(polygon_geometry):
            continue
        intersection = route_geometry.intersection(polygon_geometry)
        if intersection.isEmpty():
            continue
        for line_part in _iter_line_parts(intersection):
            if len(line_part) == 0:
                continue
            start_point = line_part[0]
            points.append({"x": float(start_point.x()), "y": float(start_point.y())})

    return points


def fill_dem(input_raster, output_path):
    _delete_qgis_dataset(output_path)
    processing.run("wbt:FillDepressions", {
        "dem": input_raster,
        "fix_flats": True,
        "output": output_path,
    })
    return output_path


def compute_flow_direction(input_raster, output_path):
    _delete_qgis_dataset(output_path)
    processing.run("wbt:D8Pointer", {
        "dem": input_raster,
        "esri_pntr": True,
        "output": output_path,
    })
    return output_path


def burn_streams_into_dem(input_raster, polygon_raster, line_raster, output_path):
    from osgeo import gdal

    input_path = _resolve_raster_path(input_raster)
    polygon_path = _resolve_raster_path(polygon_raster)
    line_path = _resolve_raster_path(line_raster)

    dem_dataset = gdal.Open(input_path, gdal.GA_ReadOnly)
    if dem_dataset is None:
        raise ValueError(f"GDAL could not open raster: {input_path}")
    polygon_dataset = gdal.Open(polygon_path, gdal.GA_ReadOnly)
    if polygon_dataset is None:
        raise ValueError(f"GDAL could not open rasterized polygon mask: {polygon_path}")
    line_dataset = gdal.Open(line_path, gdal.GA_ReadOnly)
    if line_dataset is None:
        raise ValueError(f"GDAL could not open rasterized line mask: {line_path}")

    dem_band = dem_dataset.GetRasterBand(1)
    dem_array = dem_band.ReadAsArray().astype(np.float32)
    polygon_array = polygon_dataset.GetRasterBand(1).ReadAsArray()
    line_array = line_dataset.GetRasterBand(1).ReadAsArray()
    nodata = dem_band.GetNoDataValue()
    transform = dem_dataset.GetGeoTransform()
    projection = dem_dataset.GetProjection()
    width = dem_dataset.RasterXSize
    height = dem_dataset.RasterYSize

    result_array = np.where(polygon_array == -255, dem_array, dem_array - 100.0).astype(np.float32)
    result_array = np.where(line_array == -255, result_array, dem_array - 200.0).astype(np.float32)

    if nodata is not None:
        try:
            if np.isnan(float(nodata)):
                dem_nodata_mask = np.isnan(dem_array)
            else:
                dem_nodata_mask = dem_array == float(nodata)
        except (TypeError, ValueError):
            dem_nodata_mask = None
        if dem_nodata_mask is not None:
            result_array[dem_nodata_mask] = dem_array[dem_nodata_mask]

    _delete_qgis_dataset(output_path)
    output_dataset = gdal.GetDriverByName("GTiff").Create(str(output_path), width, height, 1, gdal.GDT_Float32)
    if output_dataset is None:
        raise ValueError(f"GDAL could not create raster: {output_path}")
    output_dataset.SetGeoTransform(transform)
    if projection not in [None, ""]:
        output_dataset.SetProjection(projection)
    output_band = output_dataset.GetRasterBand(1)
    if nodata is not None:
        output_band.SetNoDataValue(float(nodata))
    output_band.WriteArray(result_array)
    output_band.FlushCache()
    output_dataset.FlushCache()

    output_dataset = None
    line_dataset = None
    polygon_dataset = None
    dem_dataset = None
    return output_path


def compute_flow_accumulation(input_raster, output_path):
    _delete_qgis_dataset(output_path)
    processing.run("wbt:D8FlowAccumulation", {
        "input": input_raster,
        "out_type": "cells",
        "log": False,
        "clip": False,
        "pntr": True,
        "esri_pntr": True,
        "output": output_path,
    })
    return output_path


def _iter_line_parts(geometry):
    if geometry.isMultipart():
        for part in geometry.asMultiPolyline():
            yield list(part)
        return

    line = geometry.asPolyline()
    if line:
        yield list(line)
        return

    vertices = [vertex for vertex in geometry.vertices()]
    if len(vertices) != 0:
        yield vertices


def locate_features_along_routes_records(points, routes, routes_id_field, search_distance, field_names=None):
    from qgis.core import QgsSpatialIndex, QgsField
    from qgis.PyQt.QtCore import QMetaType

    available_fields = points.fields()
    selected_fields = list(field_names or available_fields.names())
    field_definitions = {}
    for field_name in selected_fields:
        field_index = available_fields.indexFromName(field_name)
        if field_index >= 0:
            field_definitions[field_name] = available_fields[field_index]
    if routes_id_field not in field_definitions:
        field_definitions[routes_id_field] = QgsField(routes_id_field, QMetaType.LongLong)
    field_definitions["MEAS"] = QgsField("MEAS", QMetaType.Double)

    route_index = QgsSpatialIndex()
    route_features = {}
    for feature in routes.getFeatures():
        route_index.insertFeature(feature)
        route_features[feature.id()] = feature

    output_fields = list(selected_fields)
    for field_name in [routes_id_field, "MEAS"]:
        if field_name not in output_fields:
            output_fields.append(field_name)

    records = []
    for feature in points.getFeatures():
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue
        search_rect = geometry.boundingBox()
        search_rect.grow(search_distance)
        candidate_ids = route_index.intersects(search_rect)

        best_rid = None
        best_meas = None
        best_dist = float("inf")
        for candidate_id in candidate_ids:
            route_feature = route_features[candidate_id]
            route_geometry = route_feature.geometry()
            nearest = route_geometry.nearestPoint(geometry)
            snap_dist = nearest.distance(geometry)
            if snap_dist <= search_distance and snap_dist < best_dist:
                best_dist = snap_dist
                best_rid = route_feature[routes_id_field]
                best_meas = route_geometry.lineLocatePoint(geometry)
        if best_rid is None:
            continue

        point = geometry.asPoint()
        row = {"X": point.x(), "Y": point.y(), "_oid": feature.id()}
        for field_name in selected_fields:
            row[field_name] = feature[field_name]
        row[routes_id_field] = best_rid
        row["MEAS"] = best_meas
        records.append(row)

    return {
        "records": records,
        "field_names": output_fields,
        "field_definitions": field_definitions,
        "spatial_reference": points.sourceCrs() if hasattr(points, "sourceCrs") else None,
    }


def join_polygon_field_to_points_records(points, polygons, polygon_field, field_names=None):
    from qgis.core import QgsSpatialIndex

    available_fields = points.fields()
    selected_fields = list(field_names or available_fields.names())
    field_definitions = {}
    for field_name in selected_fields:
        field_index = available_fields.indexFromName(field_name)
        if field_index >= 0:
            field_definitions[field_name] = available_fields[field_index]

    polygon_fields = polygons.fields()
    polygon_index = polygon_fields.indexFromName(polygon_field)
    if polygon_index >= 0:
        field_definitions[polygon_field] = polygon_fields[polygon_index]

    poly_index = QgsSpatialIndex()
    polygon_features = {}
    for feature in polygons.getFeatures():
        poly_index.insertFeature(feature)
        polygon_features[feature.id()] = feature

    output_fields = list(selected_fields)
    if polygon_field not in output_fields:
        output_fields.append(polygon_field)

    records = []
    for feature in points.getFeatures():
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue
        point = geometry.asPoint()
        polygon_value = None
        for candidate_id in poly_index.intersects(geometry.boundingBox()):
            polygon_feature = polygon_features[candidate_id]
            polygon_geometry = polygon_feature.geometry()
            if polygon_geometry is None or polygon_geometry.isEmpty():
                continue
            if polygon_geometry.intersects(geometry):
                polygon_value = polygon_feature[polygon_field]
                break
        row = {"X": point.x(), "Y": point.y(), "_oid": feature.id()}
        for field_name in selected_fields:
            row[field_name] = feature[field_name]
        row[polygon_field] = polygon_value
        records.append(row)

    return {
        "records": records,
        "field_names": output_fields,
        "field_definitions": field_definitions,
        "spatial_reference": points.sourceCrs() if hasattr(points, "sourceCrs") else None,
    }


def snap_points_to_nearest_line(points, lines, field_names=None, tolerance=None):
    from . import DataManagement

    point_layer = points if hasattr(points, "getFeatures") else DataManagement.open_vector_dataset(points)
    line_layer = lines if hasattr(lines, "getFeatures") else DataManagement.open_vector_dataset(lines)

    available_point_fields = point_layer.fields()
    selected_point_fields = available_point_fields.names()
    field_definitions = {}
    for field_name in selected_point_fields:
        field_index = available_point_fields.indexFromName(field_name)
        if field_index >= 0:
            field_definitions[field_name] = available_point_fields[field_index]

    available_line_fields = line_layer.fields()
    selected_line_fields = list(field_names or available_line_fields.names())
    for field_name in selected_line_fields:
        field_index = available_line_fields.indexFromName(field_name)
        if field_index >= 0 and field_name not in field_definitions:
            field_definitions[field_name] = available_line_fields[field_index]

    line_index = QgsSpatialIndex()
    line_features = {}
    feature_order = {}
    for order, feature in enumerate(line_layer.getFeatures()):
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue
        line_index.insertFeature(feature)
        line_features[feature.id()] = feature
        feature_order[feature.id()] = order

    output_fields = list(selected_point_fields)
    for field_name in selected_line_fields:
        if field_name not in output_fields:
            output_fields.append(field_name)

    tolerance_value = None if tolerance in [None, ""] else float(tolerance)
    records = []
    for feature in point_layer.getFeatures():
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue

        point = geometry.asPoint()
        best_feature = None
        best_distance = None
        for candidate_id in _nearest_line_candidate_ids(line_index, line_features, geometry, point, tolerance_value):
            candidate_feature = line_features.get(candidate_id)
            if candidate_feature is None:
                continue
            snap_distance = _distance_point_to_line_feature(point.x(), point.y(), candidate_feature)
            if snap_distance is None:
                continue
            if tolerance_value is not None and snap_distance > tolerance_value:
                continue
            if (
                best_distance is None
                or snap_distance < best_distance - 1e-12
                or (
                    abs(snap_distance - best_distance) <= 1e-12
                    and feature_order.get(candidate_id, 0) < feature_order.get(best_feature.id(), 0)
                )
            ):
                best_feature = candidate_feature
                best_distance = snap_distance

        if best_feature is None:
            continue

        row = {"X": point.x(), "Y": point.y(), "_oid": feature.id()}
        for field_name in selected_point_fields:
            row[field_name] = feature[field_name]
        for field_name in selected_line_fields:
            row[field_name] = best_feature[field_name]
        records.append(row)

    return {
        "records": records,
        "field_names": output_fields,
        "field_definitions": field_definitions,
        "spatial_reference": _source_crs(point_layer),
    }


def sample_raster_at_points(points_records_or_dataset, raster, output_field_name):
    from osgeo import gdal
    from . import DataManagement

    point_info = _coerce_point_info(points_records_or_dataset, DataManagement)
    raster_path = _resolve_raster_path(raster)
    raster_dataset = gdal.Open(raster_path, gdal.GA_ReadOnly)
    if raster_dataset is None:
        raise ValueError(f"GDAL could not open raster: {raster_path}")

    band = raster_dataset.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    transform = raster_dataset.GetGeoTransform()
    width = int(raster_dataset.RasterXSize)
    height = int(raster_dataset.RasterYSize)
    pixel_width = abs(float(transform[1]))
    pixel_height = abs(float(transform[5]))
    x_min = float(transform[0])
    y_max = float(transform[3])
    y_min = y_max - height * pixel_height

    sampled_records = []
    for row in point_info["records"]:
        sampled_row = dict(row)
        x_value = _safe_float(row.get("X"))
        y_value = _safe_float(row.get("Y"))
        sampled_row[output_field_name] = None
        if x_value is not None and y_value is not None:
            if x_value >= x_min and x_value < x_min + width * pixel_width and y_value <= y_max and y_value >= y_min:
                column = int((x_value - x_min) / pixel_width)
                row_index = int((y_max - y_value) / pixel_height)
                if row_index == height and abs(y_value - y_min) <= 1e-9:
                    row_index = height - 1
                if 0 <= column < width and 0 <= row_index < height:
                    sample_array = band.ReadAsArray(column, row_index, 1, 1)
                    if sample_array is not None:
                        pixel_value = float(sample_array[0][0])
                        if not _is_nodata_value(pixel_value, nodata):
                            sampled_row[output_field_name] = pixel_value
        sampled_records.append(sampled_row)

    raster_dataset = None

    field_names = list(point_info.get("field_names", []))
    if output_field_name not in field_names:
        field_names.append(output_field_name)
    sampled_info = dict(point_info)
    sampled_info["records"] = sampled_records
    sampled_info["field_names"] = field_names
    return sampled_info


def _coerce_point_info(points_records_or_dataset, DataManagement):
    if isinstance(points_records_or_dataset, dict) and "records" in points_records_or_dataset:
        point_info = dict(points_records_or_dataset)
        point_info["records"] = [dict(row) for row in points_records_or_dataset.get("records", [])]
        point_info["field_names"] = list(points_records_or_dataset.get("field_names", []))
        point_info["field_definitions"] = dict(points_records_or_dataset.get("field_definitions", {}))
        return point_info

    reader = getattr(DataManagement, "read_point_dataset_any", None)
    if reader is None:
        return DataManagement.read_point_dataset(points_records_or_dataset)
    return reader(points_records_or_dataset)


def _nearest_line_candidate_ids(line_index, line_features, point_geometry, point, tolerance):
    if tolerance is not None:
        search_rect = point_geometry.boundingBox()
        search_rect.grow(float(tolerance))
        return list(line_index.intersects(search_rect))

    nearest_ids = list(line_index.nearestNeighbor(point, 1))
    if len(nearest_ids) == 0:
        return []

    nearest_feature = line_features.get(nearest_ids[0])
    if nearest_feature is None:
        return nearest_ids

    nearest_distance = _distance_point_to_line_feature(point.x(), point.y(), nearest_feature)
    if nearest_distance is None:
        return nearest_ids

    search_rect = point_geometry.boundingBox()
    search_rect.grow(float(nearest_distance))
    candidate_ids = list(line_index.intersects(search_rect))
    if nearest_ids[0] not in candidate_ids:
        candidate_ids.append(nearest_ids[0])
    return candidate_ids


def _distance_point_to_line_feature(point_x, point_y, line_feature):
    best_distance = None
    geometry = line_feature.geometry()
    if geometry is None or geometry.isEmpty():
        return None

    for part in _iter_line_parts(geometry):
        if len(part) == 1:
            distance = math.hypot(point_x - float(part[0].x()), point_y - float(part[0].y()))
            if best_distance is None or distance < best_distance:
                best_distance = distance
            continue

        for start_point, end_point in zip(part[:-1], part[1:]):
            start_x = float(start_point.x())
            start_y = float(start_point.y())
            end_x = float(end_point.x())
            end_y = float(end_point.y())
            delta_x = end_x - start_x
            delta_y = end_y - start_y
            segment_length_sq = delta_x * delta_x + delta_y * delta_y
            if segment_length_sq == 0.0:
                projected_x = start_x
                projected_y = start_y
            else:
                ratio = ((point_x - start_x) * delta_x + (point_y - start_y) * delta_y) / segment_length_sq
                ratio = max(0.0, min(1.0, ratio))
                projected_x = start_x + ratio * delta_x
                projected_y = start_y + ratio * delta_y
            distance = math.hypot(point_x - projected_x, point_y - projected_y)
            if best_distance is None or distance < best_distance:
                best_distance = distance

    return best_distance


def _safe_float(value):
    if value in [None, ""]:
        return None
    try:
        float_value = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(float_value):
        return None
    return float_value


def _is_nodata_value(value, nodata):
    if nodata is None:
        return False
    try:
        if np.isnan(float(nodata)):
            return np.isnan(value)
    except (TypeError, ValueError):
        return False
    return value == float(nodata)


def _source_crs(vector_source):
    if hasattr(vector_source, "sourceCrs"):
        try:
            return vector_source.sourceCrs()
        except Exception:
            pass
    if hasattr(vector_source, "crs"):
        try:
            return vector_source.crs()
        except Exception:
            pass
    return None


def compute_width_by_cross_sections(streamnetwork, idfield, riverbed, ineffarea, maxwidth, spacing, transects, cspoints, messages=None):
    from . import DataManagement

    try:
        stream_layer = streamnetwork if hasattr(streamnetwork, "getFeatures") else DataManagement.open_vector_dataset(streamnetwork)
        riverbed_layer = riverbed if hasattr(riverbed, "getFeatures") else DataManagement.open_vector_dataset(riverbed)
        ineffarea_layer = None
        if ineffarea not in [None, "", "#"]:
            ineffarea_layer = ineffarea if hasattr(ineffarea, "getFeatures") else DataManagement.open_vector_dataset(ineffarea)

        spacing_value = float(spacing)
        maxwidth_value = float(maxwidth)
        if spacing_value <= 0.0:
            raise ValueError("Interval between cross-sections must be greater than 0.")
        if maxwidth_value <= 0.0:
            raise ValueError("Maximum width of cross-sections must be greater than 0.")

        route_state = _width_collect_route_state(stream_layer, idfield)
        if len(route_state["routes"]) == 0:
            raise ValueError("Stream network did not contain any valid route features.")

        _width_message(messages, "Preparing river polygon inputs...")
        effective_bed = riverbed_layer
        if ineffarea_layer is not None:
            difference_result = processing.run(
                "native:difference",
                {
                    "INPUT": riverbed_layer,
                    "OVERLAY": ineffarea_layer,
                    "OUTPUT": "TEMPORARY_OUTPUT",
                },
            )
            effective_bed = DataManagement.open_vector_dataset(difference_result["OUTPUT"])

        riverbanks_result = processing.run(
            "native:polygonstolines",
            {
                "INPUT": effective_bed,
                "OUTPUT": "TEMPORARY_OUTPUT",
            },
        )
        riverbanks = DataManagement.open_vector_dataset(riverbanks_result["OUTPUT"])
        riverbanks_single_result = processing.run(
            "native:multiparttosingleparts",
            {
                "INPUT": riverbanks,
                "OUTPUT": "TEMPORARY_OUTPUT",
            },
        )
        riverbanks = DataManagement.open_vector_dataset(riverbanks_single_result["OUTPUT"])
        bank_state = _width_build_geometry_index(riverbanks)
        if len(bank_state["geometries"]) == 0:
            raise ValueError("River polygon boundaries could not be derived from the supplied riverbed polygons.")

        csfield = "CSid"
        distfield = "Distance_m"
        widthfield = "Width_m"

        _width_message(messages, "Creating confluence exclusion endpoints...")
        endpoint_rows = _width_build_endpoint_rows(route_state, bank_state, idfield, distfield, messages)

        _width_message(messages, "Generating width measurement points...")
        measurement_rows = _width_build_measurement_rows(route_state, endpoint_rows, idfield, csfield, distfield, spacing_value, messages)

        _width_message(messages, "Creating and trimming transects...")
        transect_rows = _width_build_transects(route_state, measurement_rows, bank_state, idfield, csfield, distfield, maxwidth_value, messages)

        _width_message(messages, "Removing transects that cross multiple channel branches...")
        transect_rows = _width_apply_centerline_crossing_filter(route_state, transect_rows, widthfield, messages)

        _width_message(messages, "Removing transects with excessive cross-transect intersections...")
        transect_rows = _width_remove_transect_crossings(transect_rows, 2, messages)

        _width_message(messages, "Transferring final widths back to cross-section points...")
        point_rows = _width_transfer_to_points(measurement_rows, transect_rows, idfield, csfield, distfield, widthfield, messages)

        _width_write_outputs(
            transects,
            cspoints,
            transect_rows,
            point_rows,
            route_state["id_dtype"],
            idfield,
            csfield,
            distfield,
            widthfield,
            route_state["spatial_reference"],
        )
        _width_message(messages, "Wrote {} transect(s) and {} width point(s).".format(len(transect_rows), len(point_rows)))
        return {"transects": transects, "cspoints": cspoints}
    except Exception as exc:
        if messages is not None:
            messages.add_error(str(exc))
        raise


def _width_collect_route_state(stream_layer, idfield):
    from qgis.core import QgsFeature

    field_names = stream_layer.fields().names()
    if idfield not in field_names:
        raise ValueError("Field '{}' was not found in the stream network.".format(idfield))

    routes = []
    routes_by_fid = {}
    endpoint_counts = {}
    route_index = QgsSpatialIndex()

    for feature in stream_layer.getFeatures():
        geometry = feature.geometry()
        parts = _width_geometry_parts(geometry)
        if len(parts) == 0:
            continue
        segments, total_measure = _width_build_route_segments(parts)
        if len(segments) == 0:
            continue

        route_geometry = QgsGeometry(geometry)
        route_record = {
            "fid": feature.id(),
            "rid": feature[idfield],
            "geometry": route_geometry,
            "parts": parts,
            "segments": segments,
            "length": float(total_measure),
            "start": parts[0][0],
            "end": parts[-1][-1],
        }
        routes.append(route_record)
        routes_by_fid[feature.id()] = route_record

        index_feature = QgsFeature()
        index_feature.setId(int(feature.id()))
        index_feature.setGeometry(route_geometry)
        route_index.insertFeature(index_feature)

        for endpoint in [route_record["start"], route_record["end"]]:
            key = _width_coord_key(endpoint)
            endpoint_counts[key] = endpoint_counts.get(key, 0) + 1

    return {
        "routes": routes,
        "routes_by_fid": routes_by_fid,
        "route_index": route_index,
        "endpoint_counts": endpoint_counts,
        "id_dtype": _width_infer_simple_dtype((route["rid"] for route in routes), default="int"),
        "spatial_reference": _source_crs(stream_layer),
    }


def _width_build_endpoint_rows(route_state, bank_state, idfield, distfield, messages):
    rows = []
    skipped_confluences = 0

    for route in route_state["routes"]:
        start_key = _width_coord_key(route["start"])
        end_key = _width_coord_key(route["end"])

        if route_state["endpoint_counts"].get(start_key, 0) == 1:
            rows.append(
                {
                    "X": float(route["start"][0]),
                    "Y": float(route["start"][1]),
                    idfield: route["rid"],
                    distfield: 0.0,
                    "_route_fid": route["fid"],
                }
            )
        else:
            upstream_point = _width_buffer_exit_row(route, route["start"], bank_state, idfield, distfield)
            if upstream_point is None:
                skipped_confluences += 1
            else:
                rows.append(upstream_point)

        if route_state["endpoint_counts"].get(end_key, 0) == 1:
            rows.append(
                {
                    "X": float(route["end"][0]),
                    "Y": float(route["end"][1]),
                    idfield: route["rid"],
                    distfield: float(route["length"]),
                    "_route_fid": route["fid"],
                }
            )
        else:
            downstream_point = _width_buffer_exit_row(route, route["end"], bank_state, idfield, distfield)
            if downstream_point is None:
                skipped_confluences += 1
            else:
                rows.append(downstream_point)

    if len(rows) == 0:
        raise ValueError("No endpoint or confluence boundary points could be generated from the supplied stream network.")
    if skipped_confluences != 0:
        _width_warning(
            messages,
            "{} confluence endpoint(s) could not be converted into buffered start/stop limits and were skipped.".format(
                skipped_confluences
            ),
        )
    return rows


def _width_buffer_exit_row(route, anchor_xy, bank_state, idfield, distfield):
    from qgis.core import QgsPointXY

    anchor_point = QgsPointXY(float(anchor_xy[0]), float(anchor_xy[1]))
    anchor_geometry = QgsGeometry.fromPointXY(anchor_point)
    near_distance = _width_nearest_line_distance(anchor_geometry, bank_state)
    if near_distance is None:
        return None

    buffer_geometry = anchor_geometry.buffer(float(near_distance) + 8.0, 16)
    candidate_segments = []
    for segment_geometry in _width_extract_line_geometries(route["geometry"].intersection(buffer_geometry)):
        if segment_geometry.length() > 1e-9:
            candidate_segments.append(segment_geometry)
    if len(candidate_segments) == 0:
        return None

    selected_segment = _width_select_anchor_segment(candidate_segments, anchor_geometry)
    if selected_segment is None:
        return None
    far_point = _width_segment_far_endpoint(selected_segment, anchor_point)
    if far_point is None:
        return None
    measure = _width_measure_point_along_route({"X": far_point.x(), "Y": far_point.y()}, route["parts"])
    if measure is None:
        return None

    return {
        "X": float(far_point.x()),
        "Y": float(far_point.y()),
        idfield: route["rid"],
        distfield: float(measure),
        "_route_fid": route["fid"],
    }


def _width_build_transects(route_state, measurement_rows, bank_state, idfield, csfield, distfield, maxwidth, messages):
    from qgis.core import QgsPointXY

    transects = []
    skipped = 0
    for row in measurement_rows:
        route = route_state["routes_by_fid"].get(row.get("_route_fid"))
        if route is None:
            skipped += 1
            continue

        offset_points = _width_offset_points(route["parts"], float(row[distfield]), float(maxwidth))
        if offset_points is None:
            skipped += 1
            continue

        raw_transect = QgsGeometry.fromPolylineXY(offset_points)
        measurement_geometry = QgsGeometry.fromPointXY(QgsPointXY(float(row["X"]), float(row["Y"])))
        trimmed_transect = _width_trim_transect(raw_transect, measurement_geometry, bank_state)
        if trimmed_transect is None or trimmed_transect.isEmpty() or trimmed_transect.length() <= 1e-9:
            skipped += 1
            continue
        if trimmed_transect.distance(measurement_geometry) > 0.1 + 1e-9:
            skipped += 1
            continue

        transects.append(
            {
                "geometry": trimmed_transect,
                csfield: row[csfield],
                idfield: row[idfield],
                distfield: row[distfield],
            }
        )

    if len(transects) == 0:
        raise ValueError("No valid transects could be generated from the supplied routes and river polygon.")
    if skipped != 0:
        _width_warning(messages, "{} candidate transect(s) were discarded during trimming to the riverbanks.".format(skipped))
    return transects


def _width_apply_centerline_crossing_filter(route_state, transects, widthfield, messages):
    cleaned = []
    removed = 0
    for row in transects:
        crossings = _width_collect_unique_intersection_points(
            row["geometry"],
            route_state["route_index"],
            route_state["routes_by_fid"],
        )
        if len(crossings) >= 2:
            removed += 1
            continue
        kept = dict(row)
        kept[widthfield] = float(row["geometry"].length())
        cleaned.append(kept)

    if len(cleaned) == 0:
        raise ValueError("All transects crossed multiple stream-network branches and were removed.")
    if removed != 0:
        _width_warning(messages, "{} transect(s) were removed because they intersected the stream network more than once.".format(removed))
    return cleaned


def _width_remove_transect_crossings(transects, nx, messages):
    current = []
    for index, row in enumerate(transects):
        copied = dict(row)
        copied["_temp_id"] = index + 1
        current.append(copied)

    removed_total = 0
    for threshold in range(5, int(nx), -1):
        if len(current) <= 1:
            break
        transect_index, transect_lookup = _width_build_row_geometry_index(current, "_temp_id")
        crossing_counts = {row["_temp_id"]: 0 for row in current}

        for row in current:
            row_id = row["_temp_id"]
            candidate_ids = sorted(transect_index.intersects(row["geometry"].boundingBox()))
            for candidate_id in candidate_ids:
                if candidate_id <= row_id:
                    continue
                other_row = transect_lookup.get(candidate_id)
                if other_row is None:
                    continue
                if not row["geometry"].intersects(other_row["geometry"]):
                    continue
                crossing_points = _width_unique_point_coordinates(
                    _width_extract_point_coordinates(row["geometry"].intersection(other_row["geometry"]))
                )
                if len(crossing_points) == 0:
                    continue
                crossing_counts[row_id] += len(crossing_points)
                crossing_counts[candidate_id] += len(crossing_points)

        remove_ids = {row_id for row_id, count in crossing_counts.items() if count >= threshold}
        if len(remove_ids) == 0:
            continue
        removed_total += len(remove_ids)
        current = [row for row in current if row["_temp_id"] not in remove_ids]

    if len(current) == 0:
        raise ValueError("All transects were removed during the cross-transect cleanup stage.")
    if removed_total != 0:
        _width_warning(messages, "{} transect(s) were removed during the iterative cross-transect cleanup.".format(removed_total))
    return [{key: value for key, value in row.items() if key != "_temp_id"} for row in current]


def _width_transfer_to_points(measurement_rows, transects, idfield, csfield, distfield, widthfield, messages):
    from qgis.core import QgsPointXY

    indexed_transects = []
    for index, row in enumerate(transects):
        copied = dict(row)
        copied["_temp_id"] = index + 1
        indexed_transects.append(copied)
    transect_index, transect_lookup = _width_build_row_geometry_index(indexed_transects, "_temp_id")

    point_rows = []
    missing = 0
    for row in measurement_rows:
        point_geometry = QgsGeometry.fromPointXY(QgsPointXY(float(row["X"]), float(row["Y"])))
        search_rect = point_geometry.boundingBox()
        search_rect.grow(1.0)

        best_row = None
        best_distance = None
        for candidate_id in sorted(transect_index.intersects(search_rect)):
            transect_row = transect_lookup.get(candidate_id)
            if transect_row is None:
                continue
            distance = transect_row["geometry"].distance(point_geometry)
            if distance > 1.0 + 1e-9:
                continue
            if best_distance is None or distance < best_distance - 1e-12 or (
                abs(distance - best_distance) <= 1e-12 and candidate_id < best_row["_temp_id"]
            ):
                best_row = transect_row
                best_distance = distance

        if best_row is None:
            missing += 1
            continue

        point_rows.append(
            {
                "X": float(row["X"]),
                "Y": float(row["Y"]),
                csfield: row[csfield],
                idfield: row[idfield],
                distfield: row[distfield],
                widthfield: best_row[widthfield],
            }
        )

    if len(point_rows) == 0:
        raise ValueError("No cross-section points remained within 1 meter of a surviving transect.")
    if missing != 0:
        _width_warning(messages, "{} cross-section point(s) had no surviving transect within 1 meter and were removed.".format(missing))
    return point_rows


def _width_write_outputs(transects_output, cspoints_output, transects, point_rows, id_dtype, idfield, csfield, distfield, widthfield, spatial_reference):
    from . import DataManagement

    line_features = []
    for row in transects:
        vertices = _width_line_vertices(row["geometry"])
        if len(vertices) < 2:
            continue
        line_features.append(
            {
                "attributes": {widthfield: row[widthfield]},
                "vertices": vertices,
            }
        )

    if len(line_features) == 0:
        raise ValueError("No valid transect geometries were available for output writing.")

    DataManagement.write_line_features(
        transects_output,
        line_features,
        input_info={"field_names": [], "field_definitions": {}},
        extra_fields=[{"name": widthfield, "dtype": "float"}],
        spatial_reference=spatial_reference,
    )
    DataManagement.write_bed_assessment_points(
        cspoints_output,
        point_rows,
        {"records": [], "field_names": [], "field_definitions": {}},
        [
            {"name": csfield, "dtype": "int"},
            {"name": idfield, "dtype": id_dtype},
            {"name": distfield, "dtype": "float"},
            {"name": widthfield, "dtype": "float"},
        ],
        spatial_reference=spatial_reference,
    )


def _width_build_measurement_rows(route_state, endpoint_rows, idfield, csfield, distfield, spacing, messages):
    endpoint_by_rid = {}
    for row in endpoint_rows:
        endpoint_by_rid.setdefault(row[idfield], []).append(float(row[distfield]))

    rows = []
    csid = 1
    for route in route_state["routes"]:
        length = float(route["length"])
        start_measure = float(spacing)
        stop_measure = float(length) - float(spacing)

        endpoints = endpoint_by_rid.get(route["rid"], [])
        if len(endpoints) >= 1:
            start_measure = min(endpoints)
            stop_measure = max(endpoints)

        start_measure, stop_measure = _width_adjust_measure_window(start_measure, stop_measure, length, float(spacing))
        if (stop_measure - start_measure) < 0.0:
            _width_message(messages, "La branche {0} est trop courte ou à l'envers, elle ne peut être traitée.".format(route["rid"]))
            continue

        span = stop_measure - start_measure
        if span < (3.0 * float(spacing)):
            _width_message(messages, "La branche {0} est courte, l'espacement ne sera pas respecté.".format(route["rid"]))
            if span == 0.0:
                distances = np.array([start_measure], dtype=float)
            else:
                distances = np.arange(start_measure, stop_measure + 0.0001, span / 3.0)
        else:
            _width_message(messages, "La branche {0} a été traitée avec succès.".format(route["rid"]))
            distances = np.arange(start_measure, stop_measure, float(spacing))

        if distances.shape[0] == 0:
            distances = np.array([stop_measure], dtype=float)
        if (stop_measure - float(distances[-1])) > (float(spacing) / 2.0):
            distances = np.append(distances, stop_measure)
        else:
            distances[-1] = stop_measure

        for distance_value in distances:
            x_value, y_value = _width_point_from_measure(route["parts"], float(distance_value))
            rows.append(
                {
                    "X": float(x_value),
                    "Y": float(y_value),
                    csfield: csid,
                    idfield: route["rid"],
                    distfield: float(distance_value),
                    "_route_fid": route["fid"],
                }
            )
            csid += 1

    if len(rows) == 0:
        raise ValueError("No measurement points could be generated from the supplied stream network.")
    return rows


def _width_adjust_measure_window(start_measure, stop_measure, length, spacing):
    length_value = float(length)
    start_value = float(start_measure)
    stop_value = float(stop_measure)
    spacing_value = float(spacing)

    ratio = 0.0 if length_value == 0.0 else start_value / length_value
    int_start = int((1000.0 * start_value) + 0.5)
    int_stop = int((1000.0 * stop_value) + 0.5)

    if int_start == int_stop:
        if ratio >= 0.5:
            start_value = spacing_value
        else:
            stop_value = length_value - spacing_value

    if start_value == 0.0:
        start_value = spacing_value

    int_length = int((1000.0 * length_value) + 0.5)
    if int_stop == int_length:
        stop_value = length_value - spacing_value

    return start_value, stop_value


def _width_offset_points(route_parts, distance_value, maxwidth):
    from qgis.core import QgsPointXY

    point_x, point_y = _width_point_from_measure(route_parts, distance_value)
    direction = _width_direction_from_measure(route_parts, distance_value)
    if direction is None:
        return None
    delta_x, delta_y = direction
    direction_length = math.hypot(delta_x, delta_y)
    if direction_length == 0.0:
        return None

    normal_x = -delta_y / direction_length
    normal_y = delta_x / direction_length
    half_width = float(maxwidth) / 2.0
    return [
        QgsPointXY(float(point_x) + normal_x * half_width, float(point_y) + normal_y * half_width),
        QgsPointXY(float(point_x) - normal_x * half_width, float(point_y) - normal_y * half_width),
    ]


def _width_trim_transect(raw_transect, measurement_geometry, bank_state):
    from qgis.core import QgsPointXY

    total_length = float(raw_transect.length())
    split_measures = [0.0, total_length]
    for feature_id in bank_state["index"].intersects(raw_transect.boundingBox()):
        bank_geometry = bank_state["geometries"].get(feature_id)
        if bank_geometry is None or bank_geometry.isEmpty():
            continue
        if not raw_transect.intersects(bank_geometry):
            continue
        for x_value, y_value in _width_extract_point_coordinates(raw_transect.intersection(bank_geometry)):
            split_measure = raw_transect.lineLocatePoint(QgsGeometry.fromPointXY(QgsPointXY(float(x_value), float(y_value))))
            if split_measure is None:
                continue
            split_measures.append(float(split_measure))

    split_measures = _width_unique_sorted_measures(split_measures, total_length, tolerance=1e-7)
    candidate_segments = []
    for start_measure, stop_measure in zip(split_measures[:-1], split_measures[1:]):
        if (stop_measure - start_measure) <= 1e-7:
            continue
        candidate_segments.append(_width_substring_from_straight_line(raw_transect, start_measure, stop_measure))

    if len(candidate_segments) == 0:
        candidate_segments = [raw_transect]

    touching_segments = [segment for segment in candidate_segments if segment.distance(measurement_geometry) <= 0.1 + 1e-9]
    if len(touching_segments) == 0:
        if raw_transect.distance(measurement_geometry) <= 0.1 + 1e-9:
            return raw_transect
        return None
    return max(touching_segments, key=lambda geometry: geometry.length())


def _width_substring_from_straight_line(line_geometry, start_measure, stop_measure):
    from qgis.core import QgsPointXY

    start_point = line_geometry.interpolate(float(start_measure)).asPoint()
    stop_point = line_geometry.interpolate(float(stop_measure)).asPoint()
    return QgsGeometry.fromPolylineXY(
        [
            QgsPointXY(float(start_point.x()), float(start_point.y())),
            QgsPointXY(float(stop_point.x()), float(stop_point.y())),
        ]
    )


def _width_nearest_line_distance(point_geometry, bank_state):
    point = point_geometry.asPoint()
    candidate_ids = list(bank_state["index"].nearestNeighbor(point, 8))
    if len(candidate_ids) == 0:
        candidate_ids = list(bank_state["index"].intersects(point_geometry.boundingBox()))

    best_distance = None
    for feature_id in candidate_ids:
        bank_geometry = bank_state["geometries"].get(feature_id)
        if bank_geometry is None or bank_geometry.isEmpty():
            continue
        distance = float(bank_geometry.distance(point_geometry))
        if best_distance is None or distance < best_distance:
            best_distance = distance
    return best_distance


def _width_select_anchor_segment(segment_geometries, anchor_geometry):
    best_segment = None
    best_key = None
    for segment_geometry in segment_geometries:
        start_distance, end_distance = _width_endpoint_anchor_distances(segment_geometry, anchor_geometry)
        touches_anchor = segment_geometry.distance(anchor_geometry) <= 1e-7 or min(start_distance, end_distance) <= 1e-7
        sort_key = (0 if touches_anchor else 1, min(start_distance, end_distance), -float(segment_geometry.length()))
        if best_key is None or sort_key < best_key:
            best_key = sort_key
            best_segment = segment_geometry
    return best_segment


def _width_segment_far_endpoint(segment_geometry, anchor_point):
    from qgis.core import QgsPointXY

    vertices = _width_line_vertices(segment_geometry)
    if len(vertices) < 2:
        return None
    start_point = QgsPointXY(float(vertices[0][0]), float(vertices[0][1]))
    end_point = QgsPointXY(float(vertices[-1][0]), float(vertices[-1][1]))
    if _width_xy_distance((start_point.x(), start_point.y()), (anchor_point.x(), anchor_point.y())) <= _width_xy_distance(
        (end_point.x(), end_point.y()),
        (anchor_point.x(), anchor_point.y()),
    ):
        return end_point
    return start_point


def _width_endpoint_anchor_distances(segment_geometry, anchor_geometry):
    vertices = _width_line_vertices(segment_geometry)
    if len(vertices) < 2:
        return float("inf"), float("inf")
    anchor_point = anchor_geometry.asPoint()
    start_distance = _width_xy_distance(vertices[0], (anchor_point.x(), anchor_point.y()))
    end_distance = _width_xy_distance(vertices[-1], (anchor_point.x(), anchor_point.y()))
    return start_distance, end_distance


def _width_collect_unique_intersection_points(line_geometry, spatial_index, row_lookup):
    points = []
    for candidate_id in spatial_index.intersects(line_geometry.boundingBox()):
        row = row_lookup.get(candidate_id)
        if row is None:
            continue
        other_geometry = row["geometry"]
        if other_geometry is None or other_geometry.isEmpty() or not line_geometry.intersects(other_geometry):
            continue
        points.extend(_width_extract_point_coordinates(line_geometry.intersection(other_geometry)))
    return _width_unique_point_coordinates(points)


def _width_build_row_geometry_index(rows, id_key):
    from qgis.core import QgsFeature

    spatial_index = QgsSpatialIndex()
    lookup = {}
    for row in rows:
        geometry = row.get("geometry")
        if geometry is None or geometry.isEmpty():
            continue
        feature = QgsFeature()
        feature_id = int(row[id_key])
        feature.setId(feature_id)
        feature.setGeometry(geometry)
        spatial_index.insertFeature(feature)
        lookup[feature_id] = row
    return spatial_index, lookup


def _width_build_geometry_index(layer):
    spatial_index = QgsSpatialIndex()
    geometries = {}
    for feature in layer.getFeatures():
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue
        spatial_index.insertFeature(feature)
        geometries[feature.id()] = QgsGeometry(geometry)
    return {"index": spatial_index, "geometries": geometries}


def _width_extract_line_geometries(geometry):
    from qgis.core import QgsPointXY

    if geometry is None or geometry.isEmpty():
        return []

    line_geometries = []
    collection_getter = getattr(geometry, "asGeometryCollection", None)
    if callable(collection_getter):
        try:
            collection = collection_getter()
        except Exception:
            collection = []
        if collection:
            for part_geometry in collection:
                line_geometries.extend(_width_extract_line_geometries(part_geometry))
            if len(line_geometries) != 0:
                return line_geometries

    for part in _iter_line_parts(geometry):
        if len(part) < 2:
            continue
        line_geometries.append(
            QgsGeometry.fromPolylineXY([QgsPointXY(float(point.x()), float(point.y())) for point in part])
        )
    return line_geometries


def _width_extract_point_coordinates(geometry):
    from qgis.core import QgsWkbTypes

    if geometry is None or geometry.isEmpty():
        return []

    points = []
    collection_getter = getattr(geometry, "asGeometryCollection", None)
    if callable(collection_getter):
        try:
            collection = collection_getter()
        except Exception:
            collection = []
        if collection:
            for part_geometry in collection:
                points.extend(_width_extract_point_coordinates(part_geometry))
            if len(points) != 0:
                return points

    geometry_type = geometry.type()
    if geometry_type == QgsWkbTypes.PointGeometry:
        if geometry.isMultipart():
            for point in geometry.asMultiPoint():
                points.append((float(point.x()), float(point.y())))
        else:
            point = geometry.asPoint()
            points.append((float(point.x()), float(point.y())))
        return points

    if geometry_type == QgsWkbTypes.LineGeometry:
        for part in _iter_line_parts(geometry):
            for point in part:
                points.append((float(point.x()), float(point.y())))
        return points

    for vertex in geometry.vertices():
        points.append((float(vertex.x()), float(vertex.y())))
    return points


def _width_unique_sorted_measures(values, total_length, tolerance=1e-7):
    unique_values = []
    for value in values:
        if value is None:
            continue
        normalized = max(0.0, min(float(total_length), float(value)))
        if any(abs(normalized - existing) <= tolerance for existing in unique_values):
            continue
        unique_values.append(normalized)
    unique_values.sort()

    if len(unique_values) == 0:
        return [0.0, float(total_length)]
    if unique_values[0] > tolerance:
        unique_values.insert(0, 0.0)
    if (float(total_length) - unique_values[-1]) > tolerance:
        unique_values.append(float(total_length))
    else:
        unique_values[-1] = float(total_length)
    return unique_values


def _width_unique_point_coordinates(points, tolerance=1e-7):
    unique_points = []
    for point in points:
        if point is None:
            continue
        x_value = float(point[0])
        y_value = float(point[1])
        if any(abs(x_value - existing[0]) <= tolerance and abs(y_value - existing[1]) <= tolerance for existing in unique_points):
            continue
        unique_points.append((x_value, y_value))
    return unique_points


def _width_geometry_parts(geometry):
    if geometry is None or geometry.isEmpty():
        return []

    raw_parts = []
    if geometry.isMultipart():
        try:
            raw_parts = geometry.asMultiPolyline()
        except Exception:
            raw_parts = []
    else:
        try:
            raw_parts = [geometry.asPolyline()]
        except Exception:
            raw_parts = []

    if len(raw_parts) == 0:
        vertices = [vertex for vertex in geometry.vertices()]
        raw_parts = [vertices]

    parts = []
    for raw_part in raw_parts:
        coordinates = []
        for point in raw_part:
            if point is None:
                continue
            coordinates.append((float(point.x()), float(point.y())))
        if len(coordinates) >= 2:
            parts.append(coordinates)
    return parts


def _width_build_route_segments(route_parts):
    segments = []
    total_measure = 0.0
    for part in route_parts:
        for start_point, end_point in zip(part[:-1], part[1:]):
            start_x = float(start_point[0])
            start_y = float(start_point[1])
            end_x = float(end_point[0])
            end_y = float(end_point[1])
            segment_length = math.hypot(end_x - start_x, end_y - start_y)
            segments.append(
                {
                    "start_x": start_x,
                    "start_y": start_y,
                    "end_x": end_x,
                    "end_y": end_y,
                    "start_measure": total_measure,
                    "end_measure": total_measure + segment_length,
                }
            )
            total_measure += segment_length
    return segments, total_measure


def _width_point_from_measure(route_parts, measure):
    segments, total_measure = _width_build_route_segments(route_parts)
    if len(segments) == 0:
        raise ValueError("A route geometry did not contain any valid vertices.")
    target_measure = max(0.0, min(float(measure), float(total_measure)))
    for segment in segments:
        if segment["end_measure"] >= target_measure:
            span = segment["end_measure"] - segment["start_measure"]
            if span == 0.0:
                return segment["start_x"], segment["start_y"]
            ratio = (target_measure - segment["start_measure"]) / span
            return (
                segment["start_x"] + ratio * (segment["end_x"] - segment["start_x"]),
                segment["start_y"] + ratio * (segment["end_y"] - segment["start_y"]),
            )
    last_segment = segments[-1]
    return last_segment["end_x"], last_segment["end_y"]


def _width_direction_from_measure(route_parts, measure):
    segments, total_measure = _width_build_route_segments(route_parts)
    if len(segments) == 0:
        return None
    target_measure = max(0.0, min(float(measure), float(total_measure)))
    for segment in segments:
        if segment["end_measure"] >= target_measure - 1e-12:
            delta_x = segment["end_x"] - segment["start_x"]
            delta_y = segment["end_y"] - segment["start_y"]
            if delta_x != 0.0 or delta_y != 0.0:
                return delta_x, delta_y
    for segment in reversed(segments):
        delta_x = segment["end_x"] - segment["start_x"]
        delta_y = segment["end_y"] - segment["start_y"]
        if delta_x != 0.0 or delta_y != 0.0:
            return delta_x, delta_y
    return None


def _width_measure_point_along_route(point_record, route_parts):
    point_x = float(point_record["X"])
    point_y = float(point_record["Y"])
    best_distance = None
    best_measure = None
    cumulative_length = 0.0

    for part in route_parts:
        if len(part) == 1:
            distance = math.hypot(point_x - float(part[0][0]), point_y - float(part[0][1]))
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_measure = cumulative_length
            continue

        for start_point, end_point in zip(part[:-1], part[1:]):
            start_x = float(start_point[0])
            start_y = float(start_point[1])
            end_x = float(end_point[0])
            end_y = float(end_point[1])
            delta_x = end_x - start_x
            delta_y = end_y - start_y
            segment_length_sq = delta_x * delta_x + delta_y * delta_y
            segment_length = math.sqrt(segment_length_sq)

            if segment_length_sq == 0.0:
                ratio = 0.0
                projected_x = start_x
                projected_y = start_y
            else:
                ratio = ((point_x - start_x) * delta_x + (point_y - start_y) * delta_y) / segment_length_sq
                ratio = max(0.0, min(1.0, ratio))
                projected_x = start_x + ratio * delta_x
                projected_y = start_y + ratio * delta_y

            distance = math.hypot(point_x - projected_x, point_y - projected_y)
            measure = cumulative_length + ratio * segment_length
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_measure = measure

            cumulative_length += segment_length

    return best_measure


def _width_line_vertices(geometry):
    for part in _iter_line_parts(geometry):
        if len(part) >= 2:
            return [(float(point.x()), float(point.y())) for point in part]
    return []


def _width_coord_key(point, precision=8):
    return round(float(point[0]), precision), round(float(point[1]), precision)


def _width_xy_distance(point_a, point_b):
    return math.hypot(float(point_a[0]) - float(point_b[0]), float(point_a[1]) - float(point_b[1]))


def _width_infer_simple_dtype(values, default="float"):
    for value in values:
        if value in [None, ""]:
            continue
        if isinstance(value, str):
            return "str"
        if isinstance(value, bool):
            return "int"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "int" if float(value).is_integer() else "float"
    return default


def _width_message(messages, message):
    if messages is not None:
        messages.add_message(message)


def _width_warning(messages, message):
    if messages is not None:
        messages.add_warning(message)
