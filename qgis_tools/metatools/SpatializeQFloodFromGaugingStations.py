from pathlib import Path
import sys

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFeatureSink,
    QgsFeatureSink,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsWkbTypes,
    QgsGeometry,
    QgsPointXY,
)
from qgis.PyQt.QtCore import QMetaType

sys.path.append(str(Path(__file__).resolve().parents[1]))
from metatools.LargeScaleFloodMetaTools import spatialize_q_from_gauging_stations


class SpatializeQflood(QgsProcessingAlgorithm):

    FLOWACC       = "FLOWACC"
    ROUTES        = "ROUTES"
    RID_FIELD     = "RID_FIELD"
    LINKS         = "LINKS"
    PATHPOINTS    = "PATHPOINTS"
    QSTATIONS     = "QSTATIONS"
    ID_FIELD_Q    = "ID_FIELD_Q"
    NAME_FIELD_Q  = "NAME_FIELD_Q"
    DRAINAGE_FIELD_Q = "DRAINAGE_FIELD_Q"
    RID_FIELD_Q   = "RID_FIELD_Q"
    DIST_FIELD_Q  = "DIST_FIELD_Q"
    Q_FIELD_Q     = "Q_FIELD_Q"
    BETA          = "BETA"
    OUTPUT        = "OUTPUT"

    def name(self):
        return "spatializeqflood"

    def displayName(self):
        return "Spatialize discharges from gauging stations - Q flood"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Metatools"

    def groupId(self):
        return "concordiariverlab_floodtools_metatools"

    def createInstance(self):
        return SpatializeQflood()

    def shortHelpString(self):
        return (
            "Spatialize discharges from gauging stations - Q flood\n\n"
            "Spreads a single flood discharge scenario (e.g. Q100) from gauging "
            "stations across the D8 network using the drainage area power law "
            "Q = Q_station x (A/A_station)^beta. Thin wrapper around "
            "spatialize_q_from_gauging_stations with q_field set — mirrors "
            "ArcGIS's shared execute_SpatializeQ_from_gauging_stations function "
            "called with Q_field set instead of a CSV.\n\n"
            "Qstations must already carry RID and MEAS fields (from Locate "
            "Stations Along Routes) and a discharge field (from Join flood "
            "discharge to stations).\n\n"
            "Re-run this tool once per flood discharge scenario (Q20, Q100, "
            "Q350, etc.) — the output discharge field is named after the "
            "scenario field you select.\n\n"
            "Inputs:\n"
            "- Flow accumulation: watershed-scale flow accumulation raster (e.g. lidar10m_facc)\n"
            "- D8 route feature class (e.g. routesD8)\n"
            "- RID field in routes\n"
            "- Routes D8 links (e.g. linksD8)\n"
            "- Point on route D8 (e.g. pathpointsD8)\n"
            "- Qstations: gauging stations with RID/MEAS/discharge already assigned (e.g. qstations_floods_D8)\n"
            "- Id, name, drainage area, RID, MEAS, and discharge fields in Qstations\n"
            "- Beta coefficient\n\n"
            "Output: table of points with computed discharge along the D8 network (suggested name: Qflood_D8).\n"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.FLOWACC, "Flow accumulation (lidar10m_facc)",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES, "D8 route feature class (routesD8)", [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.RID_FIELD, "RID field in routes (RID)", parentLayerParameterName=self.ROUTES,
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.LINKS, "Routes D8 links (linksD8)", types=[QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.PATHPOINTS, "Point on route D8 (pathpointsD8)", types=[QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.QSTATIONS, "Qstations (Qstations_floods_D8)", [QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ID_FIELD_Q, "Id field in Qstations", parentLayerParameterName=self.QSTATIONS,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.NAME_FIELD_Q, "Gauging station name in Qstations", parentLayerParameterName=self.QSTATIONS,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.DRAINAGE_FIELD_Q, "Drainage area in Qstations", parentLayerParameterName=self.QSTATIONS,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.RID_FIELD_Q, "RID field in Qstations", parentLayerParameterName=self.QSTATIONS,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.DIST_FIELD_Q, "MEAS field in Qstations", parentLayerParameterName=self.QSTATIONS,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.Q_FIELD_Q, "Discharge field in Qstations", parentLayerParameterName=self.QSTATIONS,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.BETA,
            "Beta coefficient (drainage area exponent)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=1.0,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Points output table (suggested name: Qflood_D8)",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        flowacc      = self.parameterAsRasterLayer(parameters, self.FLOWACC, context)
        routes       = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        rid_field    = self.parameterAsString(parameters, self.RID_FIELD, context)
        links        = self.parameterAsVectorLayer(parameters, self.LINKS, context)
        pathpoints   = self.parameterAsVectorLayer(parameters, self.PATHPOINTS, context)
        q_stations   = self.parameterAsVectorLayer(parameters, self.QSTATIONS, context)
        id_field_q   = self.parameterAsString(parameters, self.ID_FIELD_Q, context)
        name_field_q = self.parameterAsString(parameters, self.NAME_FIELD_Q, context)
        drainage_field_q = self.parameterAsString(parameters, self.DRAINAGE_FIELD_Q, context)
        rid_field_q  = self.parameterAsString(parameters, self.RID_FIELD_Q, context)
        dist_field_q = self.parameterAsString(parameters, self.DIST_FIELD_Q, context)
        q_field_q    = self.parameterAsString(parameters, self.Q_FIELD_Q, context)
        beta         = self.parameterAsDouble(parameters, self.BETA, context)

        if not all([flowacc, routes, links, pathpoints, q_stations]):
            raise QgsProcessingException("One or more input layers are invalid")

        result_points = spatialize_q_from_gauging_stations(
            flow_acc=flowacc,
            routes_d8=routes,
            rid_field_d8=rid_field,
            links_d8=links,
            d8_pathpoints=pathpoints,
            q_stations=q_stations,
            id_field_q=id_field_q,
            name_field_q=name_field_q,
            drainage_field_q=drainage_field_q,
            beta=beta,
            feedback=feedback,
            rid_field_q=rid_field_q,
            dist_field_q=dist_field_q,
            q_field=q_field_q,
        )

        out_fields = QgsFields(pathpoints.fields())
        if out_fields.indexOf("flowacc") == -1:
            out_fields.append(QgsField("flowacc", QMetaType.Double))
        if out_fields.indexOf(q_field_q) == -1:
            out_fields.append(QgsField(q_field_q, QMetaType.Double))

        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields, QgsWkbTypes.Point, routes.sourceCrs(),
        )
        if sink is None:
            raise QgsProcessingException("Could not create output sink")

        pathpoint_field_names = [f.name() for f in pathpoints.fields()]

        n_missing_geom = 0
        for pt in result_points:
            if feedback.isCanceled():
                break
            f = QgsFeature(out_fields)
            attrs = [pt.get(name) for name in pathpoint_field_names]
            attrs.append(pt.get("flowacc"))
            attrs.append(pt.get("computedQ"))
            f.setAttributes(attrs)

            x, y = pt.get("X"), pt.get("Y")
            if x is not None and y is not None:
                f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(x), float(y))))
            else:
                n_missing_geom += 1

            sink.addFeature(f, QgsFeatureSink.FastInsert)

        if n_missing_geom:
            feedback.pushWarning(
                f"{n_missing_geom} point(s) had no X/Y fields — written with no geometry."
            )

        return {self.OUTPUT: dest_id}