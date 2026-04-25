import numpy as np
from pathlib import Path
import sys
from osgeo import gdal
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
    QgsFeatureSink,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QMetaType

sys.path.append(str(Path(__file__).resolve().parents[0]))

from AssignPointToClosestPointOnRoute import assign_point_to_closest_point_on_route
from InterpolatePoints import interpolate_points
from WSsmoothing import ws_processing
from RelateNetworks import relate_networks


class ExtractWaterSurface(QgsProcessingAlgorithm):

    ROUTES_MAIN        = "ROUTES_MAIN"
    RID_FIELD          = "RID_FIELD"
    QORDER_FIELD       = "QORDER_FIELD"
    ROUTES_MAIN_LINKS  = "ROUTES_MAIN_LINKS"
    WSROUTES_D8        = "WSROUTES_D8"
    RID_FIELD_D8       = "RID_FIELD_D8"
    WSLINKS_D8         = "WSLINKS_D8"
    WS_PATHPOINTS_D8   = "WS_PATHPOINTS_D8"
    X_FIELD_PATHPOINTS = "X_FIELD_PATHPOINTS"
    Y_FIELD_PATHPOINTS = "Y_FIELD_PATHPOINTS"
    TARGET_PTS         = "TARGET_PTS"
    RID_FIELD_TARGET   = "RID_FIELD_TARGET"
    MEAS_FIELD_TARGET  = "MEAS_FIELD_TARGET"
    LIDAR_3M_FORWS     = "LIDAR_3M_FORWS"
    DEM_FOOTPRINTS     = "DEM_FOOTPRINTS"
    DEM_ID_FIELD       = "DEM_ID_FIELD"
    NET_RELATE_TABLE   = "NET_RELATE_TABLE"
    SMOOTHED_PTS       = "SMOOTHED_PTS"

    def name(self):
        return "extract_water_surface"

    def displayName(self):
        return "Extract water surface"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return ExtractWaterSurface()

    def shortHelpString(self):
        return (
            "Extract water surface\n\n"
            "Extracts water surface elevation at target points along a river network "
            "by interpolating between measured water surface values and applying "
            "hydrological smoothing. Relates the D8 flow direction network to the "
            "main routes network and performs water surface interpolation with "
            "Gaussian smoothing.\n\n"
            "Inputs:\n"
            "- Main routes network: oriented line layer with RID and flow order (routes_main)\n"
            "- RouteID field: RID\n"
            "- Flow order field: Qorder (from Order reaches tool)\n"
            "- Routes links table: DownID/UpID link table (routes_main_links)\n"
            "- D8 routes network: flow-direction-based network traces (wsroutesD8)\n"
            "- RouteID field in D8 routes: RID\n"
            "- D8 links table: DownID/UpID for D8 network (wslinksD8)\n"
            "- D8 flow points: sampled points along D8 paths (ws_pathpointsD8)\n"
            "- X field in D8 flow points: X\n"
            "- Y field in D8 flow points: Y\n"
            "- Target points: points on network with RID and MEAS (target_pts)\n"
            "- RouteID field in target points: RID\n"
            "- Measure field in target points: MEAS\n"
            "- DEM (3m corrected): corrected elevation raster (lidar3m_forws)\n"
            "- DEM footprints: polygon coverage of individual DEMs (DEM_footprints)\n"
            "- ID field in DEM footprints: field identifying each DEM (ID_DEM)\n\n"
            "Outputs:\n"
            "- net_relate_table: relates routes_main RIDs to D8 RIDs\n"
            "- smoothed_pts: water surface points with smoothed elevation values\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES_MAIN, "Main routes network (routes_main)",
            [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.RID_FIELD, "RouteID field in main routes (RID)",
            parentLayerParameterName=self.ROUTES_MAIN,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.QORDER_FIELD, "Flow order field (Qorder)",
            parentLayerParameterName=self.ROUTES_MAIN,
            defaultValue="Qorder",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES_MAIN_LINKS, "Routes links table (routes_main_links)",
            [QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.WSROUTES_D8, "D8 routes network (wsroutesD8)",
            [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.RID_FIELD_D8, "RouteID field in D8 routes (RID)",
            parentLayerParameterName=self.WSROUTES_D8,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.WSLINKS_D8, "D8 links table (wslinksD8)",
            [QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.WS_PATHPOINTS_D8, "D8 flow points (ws_pathpointsD8)",
            [QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.X_FIELD_PATHPOINTS, "X field in D8 flow points",
            parentLayerParameterName=self.WS_PATHPOINTS_D8,
            defaultValue="X",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.Y_FIELD_PATHPOINTS, "Y field in D8 flow points",
            parentLayerParameterName=self.WS_PATHPOINTS_D8,
            defaultValue="Y",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.TARGET_PTS, "Target points (target_pts)",
            [QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.RID_FIELD_TARGET, "RouteID field in target points (RID)",
            parentLayerParameterName=self.TARGET_PTS,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.MEAS_FIELD_TARGET, "Measure field in target points (MEAS)",
            parentLayerParameterName=self.TARGET_PTS,
            defaultValue="MEAS",
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.LIDAR_3M_FORWS, "DEM (lidar3m_forws)",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.DEM_FOOTPRINTS, "DEM footprints (DEM_footprints)",
            [QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.DEM_ID_FIELD, "ID field in DEM footprints (ID_DEM)",
            parentLayerParameterName=self.DEM_FOOTPRINTS,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.NET_RELATE_TABLE, "net_relate_table",
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.SMOOTHED_PTS, "smoothed_pts",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        routes_main       = self.parameterAsVectorLayer(parameters, self.ROUTES_MAIN, context)
        rid_field         = self.parameterAsString(parameters, self.RID_FIELD, context)
        qorder_field      = self.parameterAsString(parameters, self.QORDER_FIELD, context)
        routes_main_links = self.parameterAsVectorLayer(parameters, self.ROUTES_MAIN_LINKS, context)
        wsroutes_d8       = self.parameterAsVectorLayer(parameters, self.WSROUTES_D8, context)
        rid_field_d8      = self.parameterAsString(parameters, self.RID_FIELD_D8, context)
        wslinks_d8        = self.parameterAsVectorLayer(parameters, self.WSLINKS_D8, context)
        ws_pathpoints_d8  = self.parameterAsVectorLayer(parameters, self.WS_PATHPOINTS_D8, context)
        x_field           = self.parameterAsString(parameters, self.X_FIELD_PATHPOINTS, context)
        y_field           = self.parameterAsString(parameters, self.Y_FIELD_PATHPOINTS, context)
        target_pts        = self.parameterAsVectorLayer(parameters, self.TARGET_PTS, context)
        rid_field_target  = self.parameterAsString(parameters, self.RID_FIELD_TARGET, context)
        meas_field_target = self.parameterAsString(parameters, self.MEAS_FIELD_TARGET, context)
        lidar_3m_forws    = self.parameterAsRasterLayer(parameters, self.LIDAR_3M_FORWS, context)
        dem_footprints    = self.parameterAsVectorLayer(parameters, self.DEM_FOOTPRINTS, context)
        dem_id_field      = self.parameterAsString(parameters, self.DEM_ID_FIELD, context)

        if not all([routes_main, routes_main_links, wsroutes_d8, wslinks_d8,
                    ws_pathpoints_d8, target_pts, lidar_3m_forws, dem_footprints]):
            raise QgsProcessingException("One or more input layers are invalid")

        relate_rows, smoothed_rows = extract_water_surface(
            routes_main=routes_main,
            rid_field=rid_field,
            qorder_field=qorder_field,
            routes_main_links=routes_main_links,
            wsroutes_d8=wsroutes_d8,
            rid_field_d8=rid_field_d8,
            wslinks_d8=wslinks_d8,
            ws_pathpoints_d8=ws_pathpoints_d8,
            x_field=x_field,
            y_field=y_field,
            target_pts=target_pts,
            rid_field_target=rid_field_target,
            meas_field_target=meas_field_target,
            lidar_3m_forws=lidar_3m_forws,
            dem_footprints=dem_footprints,
            dem_id_field=dem_id_field,
            feedback=feedback,
        )

        # Write relate table
        relate_fields = QgsFields()
        relate_fields.append(QgsField("RID_main",   QMetaType.LongLong))
        relate_fields.append(QgsField("RID_D8",     QMetaType.LongLong))
        relate_fields.append(QgsField("PART_COUNT", QMetaType.LongLong))

        (relate_sink, relate_id) = self.parameterAsSink(
            parameters, self.NET_RELATE_TABLE, context,
            relate_fields,
            QgsWkbTypes.NoGeometry,
            routes_main.sourceCrs(),
        )
        for row in relate_rows:
            if feedback.isCanceled():
                break
            f = QgsFeature(relate_fields)
            f.setAttributes([int(row[0]), int(row[1]), int(row[2])])
            relate_sink.addFeature(f, QgsFeatureSink.FastInsert)

        # Write smoothed points
        if not smoothed_rows:
            raise QgsProcessingException("No smoothed points were produced")

        out_fields = QgsFields()
        for f in target_pts.fields():
            out_fields.append(f)
        for extra in ["lidar3m_forws", "zws_quantilecarving", "zws_smoothed"]:
            if out_fields.indexFromName(extra) < 0:
                out_fields.append(QgsField(extra, QMetaType.Double))
        if out_fields.indexFromName(dem_id_field) < 0:
            out_fields.append(QgsField(dem_id_field, QMetaType.QString))

        (smooth_sink, smooth_id) = self.parameterAsSink(
            parameters, self.SMOOTHED_PTS, context,
            out_fields,
            QgsWkbTypes.Point,
            target_pts.sourceCrs(),
        )
        for row in smoothed_rows:
            if feedback.isCanceled():
                break
            f = QgsFeature(out_fields)
            if "X" in row and "Y" in row:
                f.setGeometry(QgsGeometry.fromPointXY(
                    QgsPointXY(float(row["X"]), float(row["Y"]))
                ))
            attrs = [row.get(field.name()) for field in out_fields]
            f.setAttributes(attrs)
            smooth_sink.addFeature(f, QgsFeatureSink.FastInsert)

        return {
            self.NET_RELATE_TABLE: relate_id,
            self.SMOOTHED_PTS:     smooth_id,
        }


# =============================================================================
# Core logic
# =============================================================================

def extract_water_surface(
    routes_main,
    rid_field,
    qorder_field,
    routes_main_links,
    wsroutes_d8,
    rid_field_d8,
    wslinks_d8,
    ws_pathpoints_d8,
    x_field,
    y_field,
    target_pts,
    rid_field_target,
    meas_field_target,
    lidar_3m_forws,
    dem_footprints,
    dem_id_field,
    feedback,
):
    """
    Orchestrates water surface extraction workflow.

    Args:
        routes_main       : QgsVectorLayer - main routes with RID and Qorder
        rid_field         : str - RID field in routes_main
        qorder_field      : str - flow order field in routes_main
        routes_main_links : QgsVectorLayer - DownID/UpID link table
        wsroutes_d8       : QgsVectorLayer - D8 routes
        rid_field_d8      : str - RID field in D8 routes
        wslinks_d8        : QgsVectorLayer - D8 links table
        ws_pathpoints_d8  : QgsVectorLayer - D8 flow points with X, Y fields
        x_field           : str - X field name in D8 flow points
        y_field           : str - Y field name in D8 flow points
        target_pts        : QgsVectorLayer - target points with RID and MEAS
        rid_field_target  : str - RID field in target points
        meas_field_target : str - MEAS field in target points
        lidar_3m_forws    : QgsRasterLayer - corrected 3m DEM
        dem_footprints    : QgsVectorLayer - DEM coverage polygons
        dem_id_field      : str - ID field in DEM footprints
        feedback          : QgsProcessingFeedback

    Returns:
        (relate_rows, smoothed_rows)
        relate_rows   : list of (rid_a, rid_b, part_count)
        smoothed_rows : list of dicts with smoothed water surface values
    """

    elev_field_name = "lidar3m_forws"

    # ------------------------------------------------------------------
    # Step 1: Extract raster values to D8 flow points
    # ------------------------------------------------------------------
    feedback.pushInfo("Step 1/5: Extracting raster values to D8 flow points...")

    ds = gdal.Open(lidar_3m_forws.source())
    gt = ds.GetGeoTransform()
    band = ds.GetRasterBand(1)
    nodata = band.GetNoDataValue()

    # Check if elevation already exists on the layer
    has_elev = ws_pathpoints_d8.fields().indexFromName(elev_field_name) >= 0

    # Load all pathpoints into memory with elevation
    pathpoints_data = []
    for feat in ws_pathpoints_d8.getFeatures():
        if feedback.isCanceled():
            break
        d = {}
        for f in ws_pathpoints_d8.fields().names():
            d[f] = feat[f]
        d["X"] = float(feat[x_field])
        d["Y"] = float(feat[y_field])

        if has_elev and feat[elev_field_name] is not None:
            # Already has elevation — reuse it
            d[elev_field_name] = float(feat[elev_field_name])
        else:
            # Extract from raster
            col = int((d["X"] - gt[0]) / gt[1])
            row = int((d["Y"] - gt[3]) / gt[5])
            if 0 <= col < ds.RasterXSize and 0 <= row < ds.RasterYSize:
                val = band.ReadAsArray(col, row, 1, 1)
                if val is not None:
                    pixel_val = float(val[0][0])
                    d[elev_field_name] = None if (nodata is not None and pixel_val == nodata) else pixel_val
                else:
                    d[elev_field_name] = None
            else:
                d[elev_field_name] = None

        pathpoints_data.append(d)

    ds = None

    valid_count = sum(1 for pt in pathpoints_data if pt.get(elev_field_name) is not None)
    feedback.pushInfo(
        f"  {valid_count} / {len(pathpoints_data)} "
        f"pathpoints have valid {elev_field_name} values"
    )

    # ------------------------------------------------------------------
    # Step 2: Relate D8 network to main routes network
    # ------------------------------------------------------------------
    feedback.pushInfo("Step 2/5: Relating D8 network to main routes network...")

    relate_rows = relate_networks(
        shapefile_a=routes_main,
        rid_a=rid_field,
        shapefile_b=wsroutes_d8,
        rid_b=rid_field_d8,
        feedback=feedback,
    )

    # Build RID_main -> RID_D8 lookup from relate table
    rid_main_to_d8 = {int(r[0]): int(r[1]) for r in relate_rows}

    # ------------------------------------------------------------------
    # Step 3: Load target points and assign elevation from pathpoints
    # ------------------------------------------------------------------
    feedback.pushInfo("Step 3/5: Assigning elevation to target points from D8 flow points...")

    # Remap pathpoints D8 RIDs to main RIDs using relate table
    d8_to_rid_main = {int(r[1]): int(r[0]) for r in relate_rows}
    for pt in pathpoints_data:
        d8_rid = int(pt.get(rid_field_d8, -1))
        pt[rid_field_target] = d8_to_rid_main.get(d8_rid, -1)

    # Load target points with geometry and DEM ID
    dem_feats = list(dem_footprints.getFeatures())
    target_pts_data = []
    for feat in target_pts.getFeatures():
        if feedback.isCanceled():
            break
        d = {}
        for f in target_pts.fields().names():
            d[f] = feat[f]
        geom = feat.geometry()
        if not geom.isEmpty():
            pt = geom.asPoint()
            d["X"] = pt.x()
            d["Y"] = pt.y()
            d[dem_id_field] = None
            test_geom = QgsGeometry.fromPointXY(QgsPointXY(pt.x(), pt.y()))
            for dem_feat in dem_feats:
                if dem_feat.geometry().contains(test_geom):
                    d[dem_id_field] = dem_feat[dem_id_field]
                    break
        target_pts_data.append(d)

    # Build main routes geometry lookup
    routes_geoms = {
        int(f[rid_field]): f.geometry()
        for f in routes_main.getFeatures()
    }

    pts_assigned = assign_point_to_closest_point_on_route(
        data_points=pathpoints_data,
        data_fields=[elev_field_name],
        data_matching_fields=[rid_field_target],
        target_points=target_pts_data,
        target_rid_field=rid_field_target,
        target_dist_field=meas_field_target,
        target_matching_fields=[rid_field_target],
        routes=routes_geoms,
        rid_field=rid_field,
        stat="2-WAY CLOSEST",
        feedback=feedback,
    )
    feedback.pushInfo(f"  pts_assigned sample keys: {list(pts_assigned[0].keys()) if pts_assigned else 'empty'}")
    feedback.pushInfo(f"  pts_assigned count: {len(pts_assigned)}")
    feedback.pushInfo(f"  target_pts_data count: {len(target_pts_data)}")

    # ------------------------------------------------------------------
    # Step 4: Interpolate water surface along main routes
    # ------------------------------------------------------------------
    feedback.pushInfo("Step 4/5: Interpolating water surface along main routes...")

    # Build reaches dict
    reaches = {}
    for feat in routes_main.getFeatures():
        rid = int(feat[rid_field])
        reaches[rid] = {
            "length": feat.geometry().length(),
            "order":  int(feat[qorder_field]) if feat[qorder_field] is not None else 0,
        }

    # Build topology dicts
    downstream = {}
    upstream   = {}
    for feat in routes_main_links.getFeatures():
        down_id = int(feat["DownID"])
        up_id   = int(feat["UpID"])
        downstream[up_id] = down_id
        upstream.setdefault(down_id, []).append(up_id)

    pts_interpolated = interpolate_points(
        data_points=pts_assigned,
        pts_id="id",
        pts_rid=rid_field_target,
        pts_dist=meas_field_target,
        data_fields=[elev_field_name],
        target_points=target_pts_data,
        tgt_id="id",
        tgt_rid=rid_field_target,
        tgt_dist=meas_field_target,
        reaches=reaches,
        downstream=downstream,
        upstream=upstream,
        feedback=feedback,
    )

    # ------------------------------------------------------------------
    # Step 5: Apply Gaussian smoothing
    # ------------------------------------------------------------------
    feedback.pushInfo("Step 5/5: Applying Gaussian smoothing to water surface...")

    feedback.pushInfo(f"  pts_interpolated[0] keys: {list(pts_interpolated[0].keys())}")
    feedback.pushInfo(f"  pts_interpolated[0] lidar3m_forws: {pts_interpolated[0].get('lidar3m_forws')}")
    feedback.pushInfo(f"  pts_interpolated[0] MEAS: {pts_interpolated[0].get('MEAS')}")

    smoothed_rows = ws_processing(
        data_points=pts_interpolated,
        pts_id="id",
        pts_rid=rid_field_target,
        pts_dist=meas_field_target,
        pts_ws=elev_field_name,
        pts_dem=dem_id_field,
        reaches=reaches,
        downstream=downstream,
        upstream=upstream,
        feedback=feedback,
    )

    sample = smoothed_rows[:3]
    for pt in sample:
        feedback.pushInfo(
            f"  id={pt.get('id')} lidar3m_forws={pt.get('lidar3m_forws'):.4f} "
            f"zws_quantilecarving={pt.get('zws_quantilecarving'):.4f} "
            f"zws_smoothed={pt.get('zws_smoothed'):.4f}"
        )

    return relate_rows, smoothed_rows