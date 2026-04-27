import os
import numpy as np
from osgeo import gdal, ogr, osr
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
    QgsGeometry,
)
import processing


class FlowDirectionForWS(QgsProcessingAlgorithm):

    ROUTES_MAIN    = "ROUTES_MAIN"
    DEM            = "DEM"
    DEM_FOOTPRINTS = "DEM_FOOTPRINTS"
    OUTPUT_FOLDER  = "OUTPUT_FOLDER"

    EXIT_DIST = 25  # metres, hardcoded to match ArcGIS original

    def name(self):
        return "flowdirectionforws"

    def displayName(self):
        return "Flow Direction for Water Surface Assessment"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return FlowDirectionForWS()

    def shortHelpString(self):
        return (
            "Flow Direction for Water Surface Assessment\n\n"
            "Computes a flow direction raster for each DEM footprint, enforcing drainage "
            "toward the river outlet. For each footprint, the DEM is clipped, surrounded "
            "by an artificial wall following the exact pixel boundary, and holes are punched "
            "at all river boundary crossings. Depressions are filled using WhiteboxTools "
            "FillDepressions, then flow direction is computed using WhiteboxTools D8Pointer "
            "(ArcGIS-compatible D8 encoding). The result is clipped back to the original "
            "footprint extent and saved as a separate raster per footprint.\n\n"
            "Inputs:\n"
            "- Main route feature class: routes_main line layer\n"
            "- DEM for water surface assessment: lidar3m_forws_lakes\n"
            "- DEM footprints: polygon layer of DEM tile extents\n"
            "- Output folder: directory where flow direction rasters will be written\n\n"
            "Output:\n"
            "- One flow direction raster per footprint: fd_{oid}.tif\n"
            "  Note: WhiteboxTools must be installed and configured in QGIS Processing settings.\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterFolderDestination,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES_MAIN,
            "Input main route feature class (lines)",
            [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.DEM,
            "DEM for water surface assessment",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.DEM_FOOTPRINTS,
            "DEM footprints feature class",
            [QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUTPUT_FOLDER,
            "Output folder",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        routes_main    = self.parameterAsVectorLayer(parameters, self.ROUTES_MAIN, context)
        dem_layer      = self.parameterAsRasterLayer(parameters, self.DEM, context)
        dem_footprints = self.parameterAsVectorLayer(parameters, self.DEM_FOOTPRINTS, context)
        output_folder  = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)

        if routes_main is None:
            raise QgsProcessingException("Input routes layer is invalid")
        if dem_layer is None:
            raise QgsProcessingException("Input DEM layer is invalid")
        if dem_footprints is None:
            raise QgsProcessingException("Input DEM footprints layer is invalid")

        execute_flow_direction_for_ws(
            routes_main, dem_layer, dem_footprints, output_folder,
            self.EXIT_DIST, feedback
        )
        return {self.OUTPUT_FOLDER: output_folder}


# =============================================================================
# Helpers
# =============================================================================

def _clip_raster_to_footprint(dem_path, footprint_geom, tmp_path, nodata_val):
    """
    Clips a raster to a single polygon geometry using GDAL Warp.
    Writes result to tmp_path.
    """
    gdal.Warp(
        tmp_path,
        dem_path,
        format="GTiff",
        cutlineWKT=footprint_geom.asWkt(),
        cropToCutline=True,
        srcNodata=nodata_val,
        dstNodata=nodata_val,
        outputType=gdal.GDT_Float32,
    )


def _polygonize_valid_mask(valid_mask, gt, proj, cols, rows):
    """
    Polygonizes the valid-data pixel mask and returns the unioned OGR geometry
    of the actual data extent. Both the wall and the boundary-crossing detection
    are derived from this same geometry, so they stay consistent.

    Returns
    -------
    ogr.Geometry (Polygon or MultiPolygon) or None if no valid pixels.
    """
    bin_ds = gdal.GetDriverByName("MEM").Create("", cols, rows, 1, gdal.GDT_Byte)
    bin_ds.SetGeoTransform(gt)
    bin_ds.SetProjection(proj)
    bin_ds.GetRasterBand(1).WriteArray(valid_mask.astype(np.uint8))

    mem_driver = ogr.GetDriverByName("Memory")
    mem_ds     = mem_driver.CreateDataSource("memdata")
    srs        = osr.SpatialReference()
    srs.ImportFromWkt(proj)
    domain_layer = mem_ds.CreateLayer("domain", srs=srs, geom_type=ogr.wkbPolygon)
    domain_layer.CreateField(ogr.FieldDefn("val", ogr.OFTInteger))
    gdal.Polygonize(bin_ds.GetRasterBand(1), None, domain_layer, 0)
    bin_ds = None

    union_geom = None
    for feat in domain_layer:
        if feat.GetField("val") == 1:
            geom = feat.GetGeometryRef()
            union_geom = geom.Clone() if union_geom is None else union_geom.Union(geom)
    mem_ds = None

    return union_geom


def _build_wall_from_valid_geom(valid_geom, gt, proj, cols, rows):
    """
    Builds a wall raster (10000m) by buffering the valid-data geometry
    by 3m and rasterizing.

    Returns
    -------
    np.ndarray of float32, shape (rows, cols)
    """
    if valid_geom is None:
        return np.zeros((rows, cols), dtype=np.float32)

    buffered_wkt = valid_geom.Buffer(3.0).ExportToWkt()

    wall_ds = gdal.GetDriverByName("MEM").Create("", cols, rows, 1, gdal.GDT_Float32)
    wall_ds.SetGeoTransform(gt)
    wall_ds.SetProjection(proj)
    wall_ds.GetRasterBand(1).Fill(0)

    wall_mem  = ogr.GetDriverByName("Memory").CreateDataSource("wallmem")
    wall_srs  = osr.SpatialReference()
    wall_srs.ImportFromWkt(proj)
    wall_layer = wall_mem.CreateLayer("wall", srs=wall_srs, geom_type=ogr.wkbPolygon)
    wall_feat  = ogr.Feature(wall_layer.GetLayerDefn())
    wall_feat.SetGeometry(ogr.CreateGeometryFromWkt(buffered_wkt))
    wall_layer.CreateFeature(wall_feat)

    gdal.RasterizeLayer(wall_ds, [1], wall_layer,
                        burn_values=[10000.0], options=["ALL_TOUCHED=TRUE"])
    wall_arr = wall_ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
    wall_ds = None
    wall_mem = None

    return wall_arr


def _rasterize_polygon_to_array(geom_wkt, gt, proj, cols, rows, burn_value, all_touched=True):
    """
    Rasterizes a single polygon geometry into a numpy array.

    Returns
    -------
    np.ndarray of float32, shape (rows, cols)
    """
    mem_driver = ogr.GetDriverByName("Memory")
    mem_ds     = mem_driver.CreateDataSource("memdata")
    srs        = osr.SpatialReference()
    srs.ImportFromWkt(proj)
    mem_layer = mem_ds.CreateLayer("poly", srs=srs, geom_type=ogr.wkbPolygon)
    feat      = ogr.Feature(mem_layer.GetLayerDefn())
    feat.SetGeometry(ogr.CreateGeometryFromWkt(geom_wkt))
    mem_layer.CreateFeature(feat)

    mem_rast = gdal.GetDriverByName("MEM").Create("", cols, rows, 1, gdal.GDT_Float32)
    mem_rast.SetGeoTransform(gt)
    mem_rast.SetProjection(proj)
    mem_rast.GetRasterBand(1).Fill(0)
    mem_rast.GetRasterBand(1).SetNoDataValue(-1)

    options = ["ALL_TOUCHED=TRUE"] if all_touched else []
    gdal.RasterizeLayer(mem_rast, [1], mem_layer, burn_values=[burn_value], options=options)

    arr      = mem_rast.GetRasterBand(1).ReadAsArray().astype(np.float32)
    mem_rast = None
    mem_ds   = None
    return arr


def _write_raster(array, gt, proj, nodata_val, output_path, dtype=gdal.GDT_Float32):
    """Writes a numpy array to a GeoTIFF."""
    rows, cols = array.shape
    out_ds = gdal.GetDriverByName("GTiff").Create(output_path, cols, rows, 1, dtype)
    out_ds.SetGeoTransform(gt)
    out_ds.SetProjection(proj)
    band = out_ds.GetRasterBand(1)
    band.SetNoDataValue(nodata_val)
    band.WriteArray(array)
    out_ds.FlushCache()
    out_ds = None


def _get_boundary_crossing_geoms(valid_geom_wkt, routes_index, routes_dict):
    """
    Finds all points where routes_main crosses the boundary of the valid-pixel
    geometry (same boundary used to build the wall, so holes line up correctly).

    Parameters
    ----------
    valid_geom_wkt : str — WKT of the polygonized valid-pixel geometry
    routes_index   : QgsSpatialIndex over routes_main
    routes_dict    : dict {fid: QgsFeature} for routes_main

    Returns
    -------
    list of QgsGeometry (points), may be empty
    """
    from qgis.core import QgsPointXY

    valid_qgs_geom  = QgsGeometry.fromWkt(valid_geom_wkt)
    valid_boundary  = QgsGeometry(valid_qgs_geom.constGet().boundary())
    crossing_points = []

    candidate_ids = routes_index.intersects(valid_qgs_geom.boundingBox())
    for fid in candidate_ids:
        route_feat = routes_dict[fid]
        if not route_feat.geometry().intersects(valid_qgs_geom):
            continue
        crossing = route_feat.geometry().intersection(valid_boundary)
        if crossing.isEmpty():
            continue
        for v in crossing.vertices():
            crossing_points.append(
                QgsGeometry.fromPointXY(QgsPointXY(v.x(), v.y()))
            )

    return crossing_points


# =============================================================================
# Core logic
# =============================================================================

def execute_flow_direction_for_ws(routes_main, dem_layer, dem_footprints,
                                   output_folder, exit_dist, feedback):
    """
    Computes flow direction rasters for water surface assessment, one per DEM footprint.

    Parameters
    ----------
    routes_main     : QgsVectorLayer - main river network (lines)
    dem_layer       : QgsRasterLayer - DEM for water surface (lidar3m_forws_lakes)
    dem_footprints  : QgsVectorLayer - polygon footprints of DEM tiles
    output_folder   : str
    exit_dist       : float - buffer distance around outlet point (metres)
    feedback        : QgsProcessingFeedback
    """
    from qgis.core import QgsSpatialIndex

    os.makedirs(output_folder, exist_ok=True)

    dem_path   = dem_layer.source()
    dem_ds     = gdal.Open(dem_path)
    dem_nodata = dem_ds.GetRasterBand(1).GetNoDataValue() or -9999
    dem_ds     = None

    routes_index = QgsSpatialIndex(routes_main.getFeatures())
    routes_dict  = {f.id(): f for f in routes_main.getFeatures()}

    total = dem_footprints.featureCount()

    for i, footprint_feat in enumerate(dem_footprints.getFeatures()):
        if feedback.isCanceled():
            break

        oid = footprint_feat.id()
        feedback.pushInfo(f"Processing footprint {i + 1}/{total} (id={oid})...")
        feedback.setProgress(int((i + 1) * 100 / total))

        footprint_geom = footprint_feat.geometry()
        tmp_dir        = output_folder

        tmp_dem_clip  = os.path.join(tmp_dir, f"_tmp_dem_clip_{oid}.tif")
        tmp_wall_dem  = os.path.join(tmp_dir, f"_tmp_wall_dem_{oid}.tif")
        tmp_watershed = os.path.join(tmp_dir, f"_tmp_watershed_{oid}.tif")
        tmp_files     = [tmp_dem_clip, tmp_wall_dem, tmp_watershed]

        try:
            # Step 1: Clip DEM to footprint
            feedback.pushInfo(f"  Clipping DEM to footprint {oid}...")
            _clip_raster_to_footprint(dem_path, footprint_geom, tmp_dem_clip, dem_nodata)

            ds        = gdal.Open(tmp_dem_clip)
            gt        = ds.GetGeoTransform()
            proj      = ds.GetProjection()
            cols      = ds.RasterXSize
            rows      = ds.RasterYSize
            dem_array = ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
            ds        = None

            valid_mask = dem_array != dem_nodata

            # Step 2: Polygonize valid pixels (used for BOTH wall and crossings)
            feedback.pushInfo(f"  Polygonizing valid pixels for footprint {oid}...")
            valid_geom = _polygonize_valid_mask(valid_mask, gt, proj, cols, rows)
            if valid_geom is None:
                feedback.pushWarning(f"  No valid pixels in footprint {oid} — skipping.")
                continue
            valid_geom_wkt = valid_geom.ExportToWkt()

            # Step 3: Build wall from the same valid-pixel geometry
            feedback.pushInfo(f"  Building wall for footprint {oid}...")
            wall_arr = _build_wall_from_valid_geom(valid_geom, gt, proj, cols, rows)

            # Step 4: Find all boundary crossings against the SAME geometry
            feedback.pushInfo(f"  Finding boundary crossings for footprint {oid}...")
            crossing_points = _get_boundary_crossing_geoms(
                valid_geom_wkt, routes_index, routes_dict
            )

            outlet_arr = np.zeros((rows, cols), dtype=np.float32)
            if crossing_points:
                for pt in crossing_points:
                    pt_buffered = pt.buffer(exit_dist, 5)
                    pt_arr = _rasterize_polygon_to_array(
                        pt_buffered.asWkt(), gt, proj, cols, rows, burn_value=1.0
                    )
                    outlet_arr = np.maximum(outlet_arr, pt_arr)
                feedback.pushInfo(f"  Found {len(crossing_points)} boundary crossing(s)")
            else:
                feedback.pushWarning(
                    f"  No boundary crossings found for footprint {oid} — wall will have no exit."
                )

            # Step 5: Assemble walled DEM
            feedback.pushInfo(f"  Assembling walled DEM for footprint {oid}...")
            walled_arr = np.where(
                valid_mask,
                dem_array,
                np.where(outlet_arr > 0, dem_nodata, wall_arr)
            )
            _write_raster(walled_arr, gt, proj, dem_nodata, tmp_wall_dem)

            # Step 6: Fill depressions (WhiteboxTools)
            feedback.pushInfo(f"  Filling depressions for footprint {oid}...")
            tmp_filled = os.path.join(tmp_dir, f"_tmp_filled_{oid}.tif")
            tmp_files.append(tmp_filled)
            processing.run("wbt:BreachDepressions", {
                'dem': tmp_wall_dem,
                'output': tmp_filled,
                'max_depth': None,
                'max_length': None,
                'flat_increment': None,
                'fill_pits': True,
            })

            # Step 7: Flow direction D8 (WhiteboxTools)
            feedback.pushInfo(f"  Computing flow direction for footprint {oid}...")
            processing.run("wbt:D8Pointer", {
                'dem': tmp_filled,
                'output': tmp_watershed,
            })

            # Step 8: Read flow direction result
            feedback.pushInfo(f"  Reading flow direction result for footprint {oid}...")
            fd_ds    = gdal.Open(tmp_watershed)
            fd_array = fd_ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
            fd_ds    = None

            if fd_array.shape != dem_array.shape:
                fd_cropped = np.full(dem_array.shape, dem_nodata, dtype=np.float32)
                r = min(fd_array.shape[0], dem_array.shape[0])
                c = min(fd_array.shape[1], dem_array.shape[1])
                fd_cropped[:r, :c] = fd_array[:r, :c]
                fd_array = fd_cropped

            result_arr = np.where(valid_mask, fd_array, dem_nodata)

            out_path = os.path.join(output_folder, f"fd_{oid}.tif")
            _write_raster(result_arr, gt, proj, dem_nodata, out_path)
            feedback.pushInfo(f"  Saved: {out_path}")

        finally:
            import glob
            for tmp in tmp_files:
                for f in glob.glob(tmp + '*') + glob.glob(os.path.splitext(tmp)[0] + '.*'):
                    if os.path.exists(f):
                        os.remove(f)

    feedback.pushInfo("Flow Direction for Water Surface Assessment complete.")