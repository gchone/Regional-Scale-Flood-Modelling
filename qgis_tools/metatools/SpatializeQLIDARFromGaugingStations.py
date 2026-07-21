from pathlib import Path
import sys

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

sys.path.append(str(Path(__file__).resolve().parents[1]))
from metatools.LargeScaleFloodMetaTools import spatialize_q_from_gauging_stations


class SpatializeQLiDAR(QgsProcessingAlgorithm):
    FLOW_ACCUMULATION = "FLOW_ACCUMULATION"
    ROUTES_D8         = "ROUTES_D8"
    RID_FIELD_D8      = "RID_FIELD_D8"
    LINKS_D8          = "LINKS_D8"
    D8_PATHPOINTS     = "D8_PATHPOINTS"
    Q_STATIONS        = "Q_STATIONS"
    ID_FIELD_Q        = "ID_FIELD_Q"
    NAME_FIELD_Q      = "NAME_FIELD_Q"
    DRAINAGE_FIELD_Q  = "DRAINAGE_FIELD_Q"
    Q_DISTANCE        = "Q_DISTANCE"
    Q_CSV_FILE        = "Q_CSV_FILE"
    DEM_FOOTPRINTS    = "DEM_FOOTPRINTS"
    DEM_ID_FIELD      = "DEM_ID_FIELD"
    BETA              = "BETA"
    OUTPUT            = "OUTPUT"

    def name(self):
        return "spatialize_q_lidar"

    def displayName(self):
        return "Spatialize discharges from gauging stations - Q LiDAR"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Metatools"

    def groupId(self):
        return "concordiariverlab_floodtools_metatools"

    def createInstance(self):
        return SpatializeQLiDAR()

    def shortHelpString(self):
        return (
            "Spatialize discharges from gauging stations - Q LiDAR\n\n"
            "Computes discharge (Q) at every point along the D8 river network by "
            "interpolating from gauging station measurements. Uses drainage area "
            "ratio with power law: Q = Q_station × (A/A_station)^β\n\n"
            "Gauging station RID and MEAS values are computed internally by locating "
            "each station along the D8 routes — no pre-processing required.\n\n"
            "The CSV file must have LiDAR acquisition days as rows (ID_DEM) and "
            "gauging stations as columns:\n"
            "  ID_DEM,station1,station2,station3\n"
            "  d20150818,26.5,0.5,3.2\n"
            "  d20150819,24.4,1.0,3.7\n\n"
            "Inputs:\n"
            "- Flow accumulation raster: drainage area accumulation grid\n"
            "- routesD8: river network from flow direction\n"
            "- RID field in D8 routes\n"
            "- linksD8: DownID/UpID connectivity\n"
            "- pathpointsD8: table with X, Y fields along D8 routes\n"
            "- QStations: point layer with station locations\n"
            "- ID field in stations: unique identifier\n"
            "- Name field in stations: must match CSV column headers\n"
            "- Drainage area field: catchment area at each station (km²)\n"
            "- Maximum distance of gauging stations to the river (m)\n"
            "- CSV file: discharge measurements (see format above)\n"
            "- DEM footprints: polygon layer with ID_DEM field\n"
            "- ID_DEM field: matches CSV row IDs\n"
            "- Beta coefficient: drainage area exponent (default 1.0)\n\n"
            "Output:\n"
            "- Qpts_spatialized_D8: D8 pathpoints with computed discharge\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterFile,
            QgsProcessingParameterDistance,
            QgsProcessingParameterNumber,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterRasterLayer(
            self.FLOW_ACCUMULATION,
            "lidar10m_facc",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES_D8,
            "routesD8",
            [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.RID_FIELD_D8,
            "RID field in D8 routes",
            parentLayerParameterName=self.ROUTES_D8,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.LINKS_D8,
            "linksD8",
            [QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.D8_PATHPOINTS,
            "pathpointsD8 (table with X, Y fields)",
            [QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.Q_STATIONS,
            "QStations",
            [QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ID_FIELD_Q,
            "ID field in gauging stations",
            parentLayerParameterName=self.Q_STATIONS,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.NAME_FIELD_Q,
            "Name field in gauging stations (must match CSV headers)",
            parentLayerParameterName=self.Q_STATIONS,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.DRAINAGE_FIELD_Q,
            "Drainage area field in gauging stations (km²)",
            parentLayerParameterName=self.Q_STATIONS,
        ))
        self.addParameter(QgsProcessingParameterDistance(
            self.Q_DISTANCE,
            "Maximum distance of gauging stations to the river (m)",
            defaultValue=500.0,
            parentParameterName=self.ROUTES_D8,
        ))
        self.addParameter(QgsProcessingParameterFile(
            self.Q_CSV_FILE,
            "CSV file with discharge measurements",
            behavior=QgsProcessingParameterFile.File,
            fileFilter="CSV files (*.csv)",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.DEM_FOOTPRINTS,
            "DEM footprints",
            [QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.DEM_ID_FIELD,
            "ID_DEM field in footprints",
            parentLayerParameterName=self.DEM_FOOTPRINTS,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.BETA,
            "Beta coefficient (drainage area exponent)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=1.0,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT,
            "Qpts_spatialized_D8",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        flow_acc = self.parameterAsRasterLayer(parameters, self.FLOW_ACCUMULATION, context)
        routes_d8 = self.parameterAsVectorLayer(parameters, self.ROUTES_D8, context)
        rid_field_d8 = self.parameterAsString(parameters, self.RID_FIELD_D8, context)
        links_d8 = self.parameterAsVectorLayer(parameters, self.LINKS_D8, context)
        d8_pathpoints = self.parameterAsVectorLayer(parameters, self.D8_PATHPOINTS, context)
        q_stations = self.parameterAsVectorLayer(parameters, self.Q_STATIONS, context)
        id_field_q = self.parameterAsString(parameters, self.ID_FIELD_Q, context)
        name_field_q = self.parameterAsString(parameters, self.NAME_FIELD_Q, context)
        drainage_field = self.parameterAsString(parameters, self.DRAINAGE_FIELD_Q, context)
        q_distance = self.parameterAsDouble(parameters, self.Q_DISTANCE, context)
        csv_file = self.parameterAsString(parameters, self.Q_CSV_FILE, context)
        dem_footprints = self.parameterAsVectorLayer(parameters, self.DEM_FOOTPRINTS, context)
        dem_id_field = self.parameterAsString(parameters, self.DEM_ID_FIELD, context)
        beta = self.parameterAsDouble(parameters, self.BETA, context)

        if not all([flow_acc, routes_d8, links_d8, d8_pathpoints, q_stations, dem_footprints]):
            raise QgsProcessingException("One or more input layers are invalid")

        # Build lookup: D8 RID -> routes_main RID (ORIG_FID)
        rid_to_mainrid = {}
        for feat in routes_d8.getFeatures():
            rid_to_mainrid[int(feat[rid_field_d8])] = feat["RID_routesmain"]

        result_points = spatialize_q_from_gauging_stations(
            flow_acc=flow_acc,
            routes_d8=routes_d8,
            rid_field_d8=rid_field_d8,
            links_d8=links_d8,
            d8_pathpoints=d8_pathpoints,
            q_stations=q_stations,
            id_field_q=id_field_q,
            name_field_q=name_field_q,
            drainage_field_q=drainage_field,
            q_distance=q_distance,
            csv_file=csv_file,
            dem_footprints=dem_footprints,
            dem_id_field=dem_id_field,
            beta=beta,
            feedback=feedback,
        )

        # Build output fields
        out_fields = QgsFields()
        for f in d8_pathpoints.fields():
            if f.name() == rid_field_d8:
                out_fields.append(QgsField("RID_D8", QMetaType.LongLong))
            else:
                out_fields.append(f)

        if out_fields.indexFromName("flowacc") == -1:
            out_fields.append(QgsField("flowacc", QMetaType.Double))
        if out_fields.indexFromName("ID_DEM") == -1:
            out_fields.append(QgsField("ID_DEM", QMetaType.QString))
        if out_fields.indexFromName("RID_routesmain") == -1:
            out_fields.append(QgsField("RID_routesmain", QMetaType.LongLong))
        if out_fields.indexFromName("computedQLiDAR") == -1:
            out_fields.append(QgsField("computedQLiDAR", QMetaType.Double))

        (sink, sink_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            out_fields,
            QgsWkbTypes.Point,
            routes_d8.sourceCrs(),
        )

        for row in result_points:
            if feedback.isCanceled():
                break
            row["ID_DEM"] = row.get(dem_id_field)
            row["RID_D8"] = row.get(rid_field_d8)
            row["RID_routesmain"] = rid_to_mainrid.get(int(row.get(rid_field_d8, 0) or 0))
            row["computedQLiDAR"] = row.get("computedQ")
            f = QgsFeature(out_fields)
            if "X" in row and "Y" in row:
                f.setGeometry(QgsGeometry.fromPointXY(
                    QgsPointXY(float(row["X"]), float(row["Y"]))
                ))
            attrs = [row.get(field.name()) for field in out_fields]
            f.setAttributes(attrs)
            sink.addFeature(f, QgsFeatureSink.FastInsert)

        return {self.OUTPUT: sink_id}