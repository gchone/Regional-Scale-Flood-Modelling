import math
import warnings
import numpy as np
from scipy.stats import norm
from scipy.optimize import minimize_scalar
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

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[0]))
from QuantileRegression import quantile_carving


class WSsmoothing(QgsProcessingAlgorithm):

    ROUTES             = "ROUTES"
    LINKS              = "LINKS"
    RID_FIELD          = "RID_FIELD"
    ORDER_FIELD        = "ORDER_FIELD"
    POINTS             = "POINTS"
    PTS_ID_FIELD       = "PTS_ID_FIELD"
    PTS_RID_FIELD      = "PTS_RID_FIELD"
    PTS_DIST_FIELD     = "PTS_DIST_FIELD"
    PTS_WS_FIELD       = "PTS_WS_FIELD"
    PTS_DEM_FIELD      = "PTS_DEM_FIELD"
    QUANTILE           = "QUANTILE"
    SMOOTHING          = "SMOOTHING"
    SMOOTH_LEVEL       = "SMOOTH_LEVEL"
    UNCERTAINTY_SIGMA  = "UNCERTAINTY_SIGMA"
    UNCERTAINTY_FACTOR = "UNCERTAINTY_FACTOR"
    SLOPE_SIGMA        = "SLOPE_SIGMA"
    SLOPE_FACTOR       = "SLOPE_FACTOR"
    OUTPUT             = "OUTPUT"

    def name(self):
        return "wssmoothing"

    def displayName(self):
        return "Denoise and smooth water surface"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return WSsmoothing()

    def shortHelpString(self):
        return (
            "Denoise and smooth water surface\n\n"
            "Removes bumps in the water surface profile using quantile carving "
            "(Schwanghart and Scherler, 2017), then applies a Gaussian moving average "
            "to smooth the profile. Smoothing amount adapts to local carving corrections "
            "and slope.\n\n"
            "Inputs:\n"
            "- Input routes (lines): routes_main with M-values\n"
            "- Routes links table: DownID/UpID link table\n"
            "- RouteID field: RID\n"
            "- Flow order field: Qorder (from Order reaches tool)\n"
            "- Points with water surface: points table with elevation and DEM ID\n"
            "- ID field in points: unique point identifier\n"
            "- RouteID field in points: RID\n"
            "- Distance field in points: MEAS\n"
            "- Water surface elevation field: elevation field to smooth\n"
            "- DEM field: field identifying which DEM each point belongs to\n"
            "- Quantile for carving: lower = more aggressive (default 0.2)\n"
            "- Apply smoothing: toggle Gaussian smoothing on/off\n"
            "- Global smoothing level (standard deviation): default 600\n"
            "- Standard deviation for uncertainty measurement: default 300\n"
            "- Effect of uncertainty on smoothing (0 = no effect): default 0.85\n"
            "- Standard deviation for slope measurement: default 300\n"
            "- Effect of slope on smoothing (0 = no effect): default 2.0\n\n"
            "Output:\n"
            "- smoothed_pts: points with smoothed water surface elevation\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterNumber,
            QgsProcessingParameterBoolean,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES, "Input routes (lines)",
            [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.LINKS, "Routes links table",
            [QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.RID_FIELD, "RouteID field",
            parentLayerParameterName=self.ROUTES,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ORDER_FIELD, "Flow order field",
            parentLayerParameterName=self.ROUTES,
            defaultValue="Qorder",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.POINTS, "Points with water surface information",
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.PTS_ID_FIELD, "ID field in points",
            parentLayerParameterName=self.POINTS,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.PTS_RID_FIELD, "RouteID field in points",
            parentLayerParameterName=self.POINTS,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.PTS_DIST_FIELD, "Distance field in points",
            parentLayerParameterName=self.POINTS,
            defaultValue="MEAS",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.PTS_WS_FIELD, "Water surface elevation field",
            parentLayerParameterName=self.POINTS,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.PTS_DEM_FIELD, "DEM field in points",
            parentLayerParameterName=self.POINTS,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.QUANTILE, "Quantile for carving",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.2,
        ))
        self.addParameter(QgsProcessingParameterBoolean(
            self.SMOOTHING, "Apply smoothing",
            defaultValue=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.SMOOTH_LEVEL, "Global smoothing level (standard deviation)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=600.0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.UNCERTAINTY_SIGMA, "Standard deviation for uncertainty measurement",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=300.0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.UNCERTAINTY_FACTOR, "Effect of uncertainty on smoothing (0 = no effect)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.85,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.SLOPE_SIGMA, "Standard deviation for slope measurement",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=300.0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.SLOPE_FACTOR, "Effect of slope on smoothing (0 = no effect)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=2.0,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "smoothed_pts",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        routes       = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        links        = self.parameterAsVectorLayer(parameters, self.LINKS, context)
        rid_field    = self.parameterAsString(parameters, self.RID_FIELD, context)
        order_field  = self.parameterAsString(parameters, self.ORDER_FIELD, context)
        points       = self.parameterAsVectorLayer(parameters, self.POINTS, context)
        pts_id       = self.parameterAsString(parameters, self.PTS_ID_FIELD, context)
        pts_rid      = self.parameterAsString(parameters, self.PTS_RID_FIELD, context)
        pts_dist     = self.parameterAsString(parameters, self.PTS_DIST_FIELD, context)
        pts_ws       = self.parameterAsString(parameters, self.PTS_WS_FIELD, context)
        pts_dem      = self.parameterAsString(parameters, self.PTS_DEM_FIELD, context)
        quantile     = self.parameterAsDouble(parameters, self.QUANTILE, context)
        smoothing    = self.parameterAsBool(parameters, self.SMOOTHING, context)
        smooth_level = self.parameterAsDouble(parameters, self.SMOOTH_LEVEL, context)
        unc_sigma    = self.parameterAsDouble(parameters, self.UNCERTAINTY_SIGMA, context)
        unc_factor   = self.parameterAsDouble(parameters, self.UNCERTAINTY_FACTOR, context)
        slope_sigma  = self.parameterAsDouble(parameters, self.SLOPE_SIGMA, context)
        slope_factor = self.parameterAsDouble(parameters, self.SLOPE_FACTOR, context)

        if routes is None:
            raise QgsProcessingException("Routes layer is invalid")
        if links is None:
            raise QgsProcessingException("Links layer is invalid")
        if points is None:
            raise QgsProcessingException("Points layer is invalid")

        # Load points as list of dicts
        data_points = []
        for feat in points.getFeatures():
            d = {}
            for f in points.fields().names():
                d[f] = feat[f]
            if feat.geometry() and not feat.geometry().isEmpty():
                pt = feat.geometry().asPoint()
                d["X"] = pt.x()
                d["Y"] = pt.y()
            data_points.append(d)

        # Load reaches
        reaches = {}
        for feat in routes.getFeatures():
            rid = int(feat[rid_field])
            reaches[rid] = {
                "length": feat.geometry().length(),
                "order":  int(feat[order_field]) if feat[order_field] is not None else 0,
            }

        # Load links
        downstream = {}
        upstream   = {}
        for feat in links.getFeatures():
            down_id = int(feat["DownID"])
            up_id   = int(feat["UpID"])
            downstream[up_id] = down_id
            upstream.setdefault(down_id, []).append(up_id)

        result_rows = ws_processing(
            data_points=data_points,
            pts_id=pts_id,
            pts_rid=pts_rid,
            pts_dist=pts_dist,
            pts_ws=pts_ws,
            pts_dem=pts_dem,
            reaches=reaches,
            downstream=downstream,
            upstream=upstream,
            quantile=quantile,
            smoothing=smoothing,
            smooth_level=smooth_level,
            uncertainty_sigma=unc_sigma,
            uncertainty_factor=unc_factor,
            slope_sigma=slope_sigma,
            slope_factor=slope_factor,
            feedback=feedback,
        )

        # Build output fields
        out_fields = QgsFields()
        for f in points.fields():
            out_fields.append(f)
        out_fields.append(QgsField("zws_quantilecarving", QMetaType.Double))
        out_fields.append(QgsField("zws_smoothed",        QMetaType.Double))

        (sink, sink_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields,
            QgsWkbTypes.Point,
            routes.sourceCrs(),
        )

        for row in result_rows:
            if feedback.isCanceled():
                break
            f = QgsFeature(out_fields)
            if "X" in row and "Y" in row:
                f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(row["X"], row["Y"])))
            attrs = [row.get(field.name()) for field in out_fields]
            f.setAttributes(attrs)
            sink.addFeature(f, QgsFeatureSink.FastInsert)

        return {self.OUTPUT: sink_id}


# =============================================================================
# Helpers
# =============================================================================

def _gaussian_weighted_moving_average(
    points_list, prevcs_list, pts_dist, sigma, uncertainty_sigma,
    uncertainty_factor, slope_sigma, slope_factor, feedback=None
):
    """
    Applies a Gaussian weighted moving average to a list of cross-section dicts.
    Modifies dicts in place, adding 'zws_smoothed' and 'ws_uncertainty' keys.

    Mirrors ArcGIS Gaussian_weighted_moving_average().

    Args:
        points_list      : list of dicts — points in current DEM batch
        prevcs_list      : dict or None — last point from previous DEM batch (downstream anchor)
        pts_dist         : str — absolute distance field name (e.g. '_abs_dist')
        sigma            : float — global smoothing standard deviation
        uncertainty_sigma: float — std dev for uncertainty measurement
        uncertainty_factor: float — effect of uncertainty on smoothing
        slope_sigma      : float — std dev for slope measurement
        slope_factor     : float — effect of slope on smoothing
        feedback         : QgsProcessingFeedback or None
    """
    if prevcs_list is None:
        min_z = -math.inf
    else:
        min_z = float(prevcs_list.get("zws_smoothed", -math.inf) or -math.inf)

    distances         = np.array([float(p[pts_dist]) for p in points_list])
    values            = np.array([max(float(p["zws_quantilecarving"]), min_z)
                                  for p in points_list])
    unbreached_values = np.array([float(p["z_forws"]) for p in points_list])

    carving          = unbreached_values - values
    smoothed_values  = np.zeros_like(values)
    uncertainty_vec  = np.zeros_like(values)
    sd2_vec          = np.zeros_like(values)
    sd2              = sigma

    for i in range(len(values)):
        local_sigma = min(sigma, (distances[i] - distances[0]) * 5.0)
        local_sigma = max(local_sigma, 10.0)

        weights = norm.pdf(distances, loc=distances[i], scale=uncertainty_sigma)
        weights /= weights.sum()

        corrections = sum(np.abs(carving) * weights) ** uncertainty_factor

        if corrections < 1e-9:
            smoothed_values[i] = values[i]
        else:
            w_slope = norm.pdf(distances, loc=distances[i], scale=slope_sigma)
            w_slope /= w_slope.sum()
            delta_z     = math.exp(sum(np.abs(values[i] - values) * w_slope)) ** slope_factor
            uncertainty = corrections / delta_z
            uncertainty_vec[i] = uncertainty

            if i > 0:
                x_values = distances[0:i - 1]
                mu1 = distances[i - 1]
                sd1 = sd2
                sd2 = uncertainty * local_sigma
                mu2 = distances[i]
                F1  = norm.pdf(x_values, loc=mu1, scale=sd1)
                F2  = norm.pdf(x_values, loc=mu2, scale=sd2)

                if not np.all(F1 >= F2):
                    def objective(tested_sd2):
                        F1_ = norm.pdf(x_values, loc=mu1, scale=sd1)
                        F2_ = norm.pdf(x_values, loc=mu2, scale=tested_sd2)
                        if np.any(F1_ - F2_ < 0):
                            return np.inf
                        return -tested_sd2

                    with warnings.catch_warnings():
                        warnings.filterwarnings("ignore", category=RuntimeWarning)
                        result = minimize_scalar(
                            objective, bounds=(0.001, sd2), method="bounded"
                        )
                        sd2 = result.x if result.success else sd1
            else:
                sd2 = uncertainty * local_sigma

            sd2_vec[i] = sd2
            weights = norm.pdf(distances, loc=distances[i], scale=sd2)
            weights /= weights.sum()
            smoothed_values[i] = np.sum(weights * values)

            if i > 0 and smoothed_values[i] < smoothed_values[i - 1]:
                smoothed_values[i] = smoothed_values[i - 1]

    for i, pt in enumerate(points_list):
        pt["zws_smoothed"]   = float(smoothed_values[i])
        pt["ws_uncertainty"] = float(uncertainty_vec[i])


# =============================================================================
# Core logic
# =============================================================================

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
):
    """
    Removes bumps in the water surface profile using quantile carving, then
    optionally applies a Gaussian moving average to smooth the profile.
    Mirrors ArcGIS execute_WSprocessing but works with Python dicts.

    Both quantile carving and Gaussian smoothing are done per DEM segment,
    traversing the network downstream to upstream. The last point of each
    processed DEM batch (prevcs_list) serves as the downstream anchor for
    the next batch, matching the ArcGIS restartdown logic.

    Args:
        data_points      : list of dicts — points with elevation and DEM ID fields
        pts_id           : str — ID field name
        pts_rid          : str — RID field name
        pts_dist         : str — distance field name
        pts_ws           : str — water surface elevation field name
        pts_dem          : str — DEM ID field name
        reaches          : dict of rid -> {'length': float, 'order': int}
        downstream       : dict of rid -> down_rid
        upstream         : dict of rid -> [up_rids]
        quantile         : float — quantile for carving (default 0.2)
        smoothing        : bool — apply Gaussian smoothing (default True)
        smooth_level     : float — smoothing standard deviation (default 600)
        uncertainty_sigma: float — std dev for uncertainty (default 300)
        uncertainty_factor: float — uncertainty weight (default 0.85)
        slope_sigma      : float — std dev for slope (default 300)
        slope_factor     : float — slope weight (default 2.0)
        feedback         : QgsProcessingFeedback or None

    Returns:
        list of dicts — points with 'zws_quantilecarving' and 'zws_smoothed' added
    """
    # Initialise working fields on every point
    for pt in data_points:
        pt["z_forws"]             = float(pt.get(pts_ws) or 0)
        pt["zws_quantilecarving"] = float(pt.get(pts_ws) or 0)
        pt["zws_smoothed"]        = float(pt.get(pts_ws) or 0)

    # Index points by RID
    data_by_rid = {}
    for pt in data_points:
        rid = int(pt[pts_rid])
        data_by_rid.setdefault(rid, []).append(pt)

    # Traversal order: downstream → upstream
    all_rids        = set(reaches.keys())
    downstream_ends = all_rids - set(downstream.keys())

    def browse_down_to_up(rid):
        yield rid
        for up_rid in sorted(
            upstream.get(rid, []),
            key=lambda r: reaches.get(r, {}).get("order", 999)
        ):
            yield from browse_down_to_up(up_rid)

    for end_rid in downstream_ends:
        # --- State for this drainage path ---
        prev_dem_id       = None
        prevcs_list       = None   # last point of the previous DEM batch (downstream anchor)
        current_list      = []
        reach_dist_offset = 0.0
        prev_rid          = None
        prev_cs           = None
        restartdown       = False

        for rid in browse_down_to_up(end_rid):
            if feedback and feedback.isCanceled():
                break

            reach = reaches.get(rid)
            if reach is None:
                continue

            # Accumulate absolute-distance offset when crossing reach boundaries
            if prev_rid is not None:
                reach_dist_offset += reaches.get(prev_rid, {}).get("length", 0.0)
                if restartdown:
                    prevcs_list = prev_cs
                    restartdown = False
                # If current reach's downstream is not prev_rid, we've switched branches
                # Reset prevcs_list to avoid contaminating the new branch
                if downstream.get(rid) != prev_rid:
                    prevcs_list = None
                    restartdown = False
            prev_rid = rid

            pts_this_reach = sorted(
                data_by_rid.get(rid, []),
                key=lambda p: float(p[pts_dist])
            )

            is_upstream_end = rid not in upstream
            end_node        = pts_this_reach[-1] if pts_this_reach else None

            for pt in pts_this_reach:
                dem_id = pt.get(pts_dem)

                # DEM boundary — flush current batch
                if prev_dem_id is not None and dem_id != prev_dem_id:
                    if current_list:
                        quantile_carving(
                            current_list, prevcs_list, "_abs_dist", quantile, feedback
                        )
                        if smoothing:
                            _gaussian_weighted_moving_average(
                                current_list, prevcs_list, "_abs_dist",
                                smooth_level, uncertainty_sigma,
                                uncertainty_factor, slope_sigma, slope_factor,
                                feedback=feedback,
                            )
                    current_list = []
                    prevcs_list  = None   # no anchor for next batch after DEM change
                    restartdown  = False

                # Assign absolute distance for this batch
                pt["_abs_dist"] = float(pt[pts_dist]) + reach_dist_offset
                prev_dem_id = dem_id
                current_list.append(pt)

                # Upstream end of network — flush final batch
                if is_upstream_end and pt is end_node:
                    quantile_carving(
                        current_list, prevcs_list, "_abs_dist", quantile, feedback
                    )
                    if smoothing:
                        _gaussian_weighted_moving_average(
                            current_list, prevcs_list, "_abs_dist",
                            smooth_level, uncertainty_sigma,
                            uncertainty_factor, slope_sigma, slope_factor,
                            feedback=feedback,
                        )
                    current_list = []
                    prev_dem_id  = None
                    restartdown  = True   # next reach will set prevcs_list = prev_cs

                prev_cs = pt

    return data_points