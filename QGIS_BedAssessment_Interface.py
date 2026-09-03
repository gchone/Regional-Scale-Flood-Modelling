from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))
from BedAssessment import *
import QGIStools
from QGIS_Messages import Messages

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)


class QGIS_BedAssessment(QgsProcessingAlgorithm):
    ROUTES = "ROUTES"
    RID_FIELD = "RID_FIELD"
    ORDER_FIELD = "ORDER_FIELD"
    LINKS = "LINKS"
    POINTS = "POINTS"
    ID_FIELD = "ID_FIELD"
    RID_FIELD_PT = "RID_FIELD_PT"
    DIST_FIELD = "DIST_FIELD"
    Q_FIELD = "Q_FIELD"
    W_FIELD = "W_FIELD"
    WS_FIELD = "WS_FIELD"
    DEM_FIELD = "DEM_FIELD"
    MANNING = "MANNING"
    MIN_SLOPE = "MIN_SLOPE"
    OUTPUT = "OUTPUT"

    def name(self):
        return "bedassessment"

    def displayName(self):
        return "Bed Assessment"

    def group(self):
        return "Large Scale Flood Modelling Toolbox"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox"

    def createInstance(self):
        return QGIS_BedAssessment()

    def shortHelpString(self):
        return (
            "Bed Assessment\n\n"
            "Estimates bed elevation at each cross-section point using the ArcGIS-authoritative "
            "inverse 1D hydraulic solver with recursive cross-section oversampling when Froude "
            "number changes too sharply between adjacent sections.\n\n"
            "Inputs:\n"
            "- Route feature class: oriented route network (e.g. routes_main)\n"
            "- RouteID field: RID\n"
            "- Order field: Qorder\n"
            "- Links table: DownID/UpID connectivity (e.g. routes_main_links)\n"
            "- Points: joined input points (e.g. bathy_input_pts)\n"
            "- ID field in points: id\n"
            "- RID field in points: RID\n"
            "- Distance field in points: MEAS\n"
            "- Discharge field: computedQLiDAR\n"
            "- Width field: Width\n"
            "- Water surface field: zws_smoothed\n"
            "- DEM ID field: ID_DEM\n"
            "- Manning's n coefficient (default 0.03)\n"
            "- Minimum energy slope in flat areas (default 0.00001)\n\n"
            "Output:\n"
            "- bathy_pts: points with computed bed elevation and hydraulic variables "
            "(solver, y, R, v, z, h, s, Fr)\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterNumber,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES, "Route feature class (e.g. routes_main)",
            [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.RID_FIELD, "RouteID field",
            parentLayerParameterName=self.ROUTES,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ORDER_FIELD, "Order field",
            parentLayerParameterName=self.ROUTES,
            defaultValue="Qorder",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.LINKS, "Links table (e.g. routes_main_links)",
            [QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.POINTS, "Points (e.g. bathy_input_pts)",
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ID_FIELD, "ID field in points",
            parentLayerParameterName=self.POINTS,
            defaultValue="id",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.RID_FIELD_PT, "RID field in points",
            parentLayerParameterName=self.POINTS,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.DIST_FIELD, "Distance field in points",
            parentLayerParameterName=self.POINTS,
            defaultValue="MEAS",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.Q_FIELD, "Discharge field (computedQLiDAR)",
            parentLayerParameterName=self.POINTS,
            defaultValue="computedQLiDAR",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.W_FIELD, "Width field",
            parentLayerParameterName=self.POINTS,
            defaultValue="Width",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.WS_FIELD, "Water surface field (zws_smoothed)",
            parentLayerParameterName=self.POINTS,
            defaultValue="zws_smoothed",
        ))
        self.addParameter(QgsProcessingParameterField(
            self.DEM_FIELD, "DEM ID field",
            parentLayerParameterName=self.POINTS,
            defaultValue="ID_DEM",
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.MANNING, "Manning's n coefficient",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.03,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.MIN_SLOPE, "Minimum energy slope in flat areas",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.00001,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "bathy_pts",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        routes = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        rid_field = self.parameterAsString(parameters, self.RID_FIELD, context)
        order_field = self.parameterAsString(parameters, self.ORDER_FIELD, context)
        links = self.parameterAsVectorLayer(parameters, self.LINKS, context)
        points = self.parameterAsVectorLayer(parameters, self.POINTS, context)
        id_field = self.parameterAsString(parameters, self.ID_FIELD, context)
        rid_pt = self.parameterAsString(parameters, self.RID_FIELD_PT, context)
        dist_field = self.parameterAsString(parameters, self.DIST_FIELD, context)
        q_field = self.parameterAsString(parameters, self.Q_FIELD, context)
        w_field = self.parameterAsString(parameters, self.W_FIELD, context)
        ws_field = self.parameterAsString(parameters, self.WS_FIELD, context)
        dem_field = self.parameterAsString(parameters, self.DEM_FIELD, context)
        manning = self.parameterAsDouble(parameters, self.MANNING, context)
        min_slope = self.parameterAsDouble(parameters, self.MIN_SLOPE, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        for layer, name in [(routes, "Routes"), (links, "Links"), (points, "Points")]:
            if layer is None:
                raise QgsProcessingException(f"{name} layer is invalid")

        _check_no_nulls(points, q_field, w_field, ws_field, dem_field)

        result = execute_BedAssessment(
            routes,
            rid_field,
            order_field,
            links,
            points,
            id_field,
            rid_pt,
            dist_field,
            q_field,
            w_field,
            ws_field,
            dem_field,
            manning,
            min_slope,
            output_path,
            QGIStools,
            Messages(feedback),
        )
        return {self.OUTPUT: result}


def _check_no_nulls(points_layer, q_field, w_field, ws_field, dem_field, nodata_values=(-999,)):
    fields_to_check = [q_field, w_field, ws_field, dem_field]
    null_counts = {field_name: 0 for field_name in fields_to_check}
    for feature in points_layer.getFeatures():
        for field_name in fields_to_check:
            value = feature[field_name]
            if value is None or value in nodata_values:
                null_counts[field_name] += 1

    bad_fields = {field_name: count for field_name, count in null_counts.items() if count > 0}
    if bad_fields:
        detail = "; ".join("'{}': {} NoData value(s)".format(field_name, count) for field_name, count in bad_fields.items())
        raise QgsProcessingException(
            "Bed Assessment cannot run: the points layer contains NoData in required field(s) — {}. "
            "Resolve these values (e.g. exclude or fill the affected points) before re-running.".format(detail)
        )
