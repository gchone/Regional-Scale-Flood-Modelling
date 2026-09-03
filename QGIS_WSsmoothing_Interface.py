from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))
from WSsmoothing import *
import QGIStools
from QGIS_Messages import Messages

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)


class QGIS_WSsmoothing(QgsProcessingAlgorithm):
    ROUTES = "ROUTES"
    LINKS = "LINKS"
    RID_FIELD = "RID_FIELD"
    ORDER_FIELD = "ORDER_FIELD"
    POINTS = "POINTS"
    PTS_ID_FIELD = "PTS_ID_FIELD"
    PTS_RID_FIELD = "PTS_RID_FIELD"
    PTS_DIST_FIELD = "PTS_DIST_FIELD"
    PTS_WS_FIELD = "PTS_WS_FIELD"
    PTS_DEM_FIELD = "PTS_DEM_FIELD"
    QUANTILE = "QUANTILE"
    SMOOTHING = "SMOOTHING"
    SMOOTH_LEVEL = "SMOOTH_LEVEL"
    UNCERTAINTY_SIGMA = "UNCERTAINTY_SIGMA"
    UNCERTAINTY_FACTOR = "UNCERTAINTY_FACTOR"
    SLOPE_SIGMA = "SLOPE_SIGMA"
    SLOPE_FACTOR = "SLOPE_FACTOR"
    OUTPUT = "OUTPUT"

    def name(self):
        return "wssmoothing"

    def displayName(self):
        return "Denoise and smooth water surface"

    def group(self):
        return "Large Scale Flood Modelling Toolbox - Detailed Tools"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox_detailed_tools"

    def createInstance(self):
        return QGIS_WSsmoothing()

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

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.ROUTES,
                "Input routes (lines)",
                [QgsProcessing.TypeVectorLine],
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.LINKS,
                "Routes links table",
                [QgsProcessing.TypeVector],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.RID_FIELD,
                "RouteID field",
                parentLayerParameterName=self.ROUTES,
                defaultValue="RID",
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.ORDER_FIELD,
                "Flow order field",
                parentLayerParameterName=self.ROUTES,
                defaultValue="Qorder",
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.POINTS,
                "Points with water surface information",
                [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVector],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.PTS_ID_FIELD,
                "ID field in points",
                parentLayerParameterName=self.POINTS,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.PTS_RID_FIELD,
                "RouteID field in points",
                parentLayerParameterName=self.POINTS,
                defaultValue="RID",
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.PTS_DIST_FIELD,
                "Distance field in points",
                parentLayerParameterName=self.POINTS,
                defaultValue="MEAS",
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.PTS_WS_FIELD,
                "Water surface elevation field",
                parentLayerParameterName=self.POINTS,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.PTS_DEM_FIELD,
                "DEM field in points",
                parentLayerParameterName=self.POINTS,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.QUANTILE,
                "Quantile for carving",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0.2,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.SMOOTHING,
                "Apply smoothing",
                defaultValue=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.SMOOTH_LEVEL,
                "Global smoothing level (standard deviation)",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=600.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.UNCERTAINTY_SIGMA,
                "Standard deviation for uncertainty measurement",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=300.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.UNCERTAINTY_FACTOR,
                "Effect of uncertainty on smoothing (0 = no effect)",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0.85,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.SLOPE_SIGMA,
                "Standard deviation for slope measurement",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=300.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.SLOPE_FACTOR,
                "Effect of slope on smoothing (0 = no effect)",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=2.0,
            )
        )
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, "smoothed_pts"))

    def processAlgorithm(self, parameters, context, feedback):
        routes = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        links = self.parameterAsVectorLayer(parameters, self.LINKS, context)
        rid_field = self.parameterAsString(parameters, self.RID_FIELD, context)
        order_field = self.parameterAsString(parameters, self.ORDER_FIELD, context)
        points = self.parameterAsVectorLayer(parameters, self.POINTS, context)
        pts_id = self.parameterAsString(parameters, self.PTS_ID_FIELD, context)
        pts_rid = self.parameterAsString(parameters, self.PTS_RID_FIELD, context)
        pts_dist = self.parameterAsString(parameters, self.PTS_DIST_FIELD, context)
        pts_ws = self.parameterAsString(parameters, self.PTS_WS_FIELD, context)
        pts_dem = self.parameterAsString(parameters, self.PTS_DEM_FIELD, context)
        quantile = self.parameterAsDouble(parameters, self.QUANTILE, context)
        smoothing = self.parameterAsBool(parameters, self.SMOOTHING, context)
        smooth_level = self.parameterAsDouble(parameters, self.SMOOTH_LEVEL, context)
        uncertainty_sigma = self.parameterAsDouble(parameters, self.UNCERTAINTY_SIGMA, context)
        uncertainty_factor = self.parameterAsDouble(parameters, self.UNCERTAINTY_FACTOR, context)
        slope_sigma = self.parameterAsDouble(parameters, self.SLOPE_SIGMA, context)
        slope_factor = self.parameterAsDouble(parameters, self.SLOPE_FACTOR, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        if routes is None:
            raise QgsProcessingException("Routes layer is invalid")
        if links is None:
            raise QgsProcessingException("Links layer is invalid")
        if points is None:
            raise QgsProcessingException("Points layer is invalid")

        result = execute_WSprocessing(
            routes,
            links,
            rid_field,
            order_field,
            points,
            pts_id,
            pts_rid,
            pts_dist,
            pts_ws,
            pts_dem,
            output_path,
            QGIStools,
            Messages(feedback),
            quantile=quantile,
            smooth_level=smooth_level,
            uncertainty_sigma=uncertainty_sigma,
            uncertainty_factor=uncertainty_factor,
            slope_sigma=slope_sigma,
            slope_factor=slope_factor,
            smoothing=smoothing,
        )
        return {self.OUTPUT: result}
