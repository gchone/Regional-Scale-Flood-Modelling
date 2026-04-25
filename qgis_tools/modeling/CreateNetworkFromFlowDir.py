from pathlib import Path
import sys
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
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

from tree_qgis.TreeTools import tree_from_flowdir


class CreateNetworkFromFlowDir(QgsProcessingAlgorithm):

    FLOWDIR      = "FLOWDIR"
    FROM_POINTS  = "FROM_POINTS"
    SPLIT_PTS    = "SPLIT_PTS"
    RID_FIELD    = "RID_FIELD"
    TOLERANCE    = "TOLERANCE"
    WS_ROUTES    = "WS_ROUTES"
    WS_LINKS     = "WS_LINKS"
    WS_PATHPTS   = "WS_PATHPTS"

    def name(self):
        return "create_network_from_flow_direction_raster"

    def displayName(self):
        return "Create network from flow direction raster"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return CreateNetworkFromFlowDir()

    def shortHelpString(self):
        return (
            "Create network from flow direction raster\n\n"
            "Creates a river network data structure from a GRASS r.watershed "
            "drainage raster, tracing flow paths from the provided from-points "
            "downstream until confluence or raster edge.\n\n"
            "Inputs:\n"
            "- Flow direction raster: D8 or D4 flow direction raster (lidar3m_fd)\n"
            "- From points: headwater seeds (from_pts)\n"
            "- Split points (optional): split-point seeds (splits)\n"
            "- RouteID field: RID\n"
            "- Tolerance: max snap distance for split points in metres (default 10000)\n\n"
            "Outputs:\n"
            "- wsroutesD8: oriented network line layer\n"
            "- wslinksD8: DownID/UpID link table\n"
            "- ws_pathpointsD8: table of flow direction pixels along flow paths\n\n"
            "NB: If there are issues with certain areas, rerun Flow Direction for "
            "Water Surface Assessment for the affected footprints.\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessing,
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterNumber,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterRasterLayer(
            self.FLOWDIR,
            "Flow direction raster (lidar3m_fd)",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.FROM_POINTS,
            "From points (from_pts)",
            [QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.SPLIT_PTS,
            "Split points (splits, optional)",
            [QgsProcessing.TypeVectorPoint],
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.RID_FIELD,
            "RouteID field",
            parentLayerParameterName=self.FROM_POINTS,
            defaultValue="RID",
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.TOLERANCE,
            "Tolerance for split points (metres)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=10000.0,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.WS_ROUTES,
            "wsroutesD8",
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.WS_LINKS,
            "wslinksD8",
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.WS_PATHPTS,
            "ws_pathpointsD8",
        ))

    # =============================================================================
    # Core logic
    # =============================================================================

    def processAlgorithm(self, parameters, context, feedback):
        flowdir     = self.parameterAsRasterLayer(parameters, self.FLOWDIR, context)
        from_points = self.parameterAsVectorLayer(parameters, self.FROM_POINTS, context)
        split_pts   = self.parameterAsVectorLayer(parameters, self.SPLIT_PTS, context)
        rid_field   = self.parameterAsString(parameters, self.RID_FIELD, context)
        tolerance   = self.parameterAsDouble(parameters, self.TOLERANCE, context)

        if flowdir is None:
            raise QgsProcessingException("Flow direction raster is invalid")
        if from_points is None:
            raise QgsProcessingException("From points layer is invalid")

        fp_features    = list(from_points.getFeatures())
        split_features = list(split_pts.getFeatures()) if split_pts else []

        route_features, links_rows, points_rows = tree_from_flowdir(
            r_flow_dir=flowdir,
            fp_features=fp_features,
            split_features=split_features,
            rid_field=rid_field,
            crs=from_points.sourceCrs(),
            tolerance=tolerance,
            feedback=feedback,
        )

        # Routes sink
        route_fields = QgsFields()
        route_fields.append(QgsField(rid_field,  QMetaType.LongLong))
        route_fields.append(QgsField("ORIG_FID", QMetaType.LongLong))

        (routes_sink, routes_id) = self.parameterAsSink(
            parameters, self.WS_ROUTES, context,
            route_fields,
            QgsWkbTypes.LineString,
            from_points.sourceCrs(),
        )
        for f in route_features:
            if feedback.isCanceled():
                break
            routes_sink.addFeature(f, QgsFeatureSink.FastInsert)

        # Links sink
        link_fields = QgsFields()
        link_fields.append(QgsField("DownID", QMetaType.LongLong))
        link_fields.append(QgsField("UpID",   QMetaType.LongLong))

        (links_sink, links_id) = self.parameterAsSink(
            parameters, self.WS_LINKS, context,
            link_fields,
            QgsWkbTypes.NoGeometry,
            from_points.sourceCrs(),
        )
        for down_id, up_id in links_rows:
            if feedback.isCanceled():
                break
            lf = QgsFeature(link_fields)
            lf.setAttributes([int(down_id), int(up_id)])
            links_sink.addFeature(lf, QgsFeatureSink.FastInsert)

        # Path points sink
        path_fields = QgsFields()
        path_fields.append(QgsField("id",     QMetaType.LongLong))
        path_fields.append(QgsField("RID",    QMetaType.LongLong))
        path_fields.append(QgsField("dist",   QMetaType.Double))
        path_fields.append(QgsField("offset", QMetaType.Double))
        path_fields.append(QgsField("X",      QMetaType.Double))
        path_fields.append(QgsField("Y",      QMetaType.Double))
        path_fields.append(QgsField("row",    QMetaType.LongLong))
        path_fields.append(QgsField("col",    QMetaType.LongLong))

        (pathpts_sink, pathpts_id) = self.parameterAsSink(
            parameters, self.WS_PATHPTS, context,
            path_fields,
            QgsWkbTypes.Point,
            from_points.sourceCrs(),
        )
        for row in points_rows:
            if feedback.isCanceled():
                break
            pf = QgsFeature(path_fields)
            pf.setGeometry(
                QgsGeometry.fromPointXY(QgsPointXY(float(row[4]), float(row[5])))
            )
            pf.setAttributes([
                int(row[0]), int(row[1]), float(row[2]), float(row[3]),
                float(row[4]), float(row[5]), int(row[6]), int(row[7])
            ])
            pathpts_sink.addFeature(pf, QgsFeatureSink.FastInsert)

        return {
            self.WS_ROUTES:  routes_id,
            self.WS_LINKS:   links_id,
            self.WS_PATHPTS: pathpts_id,
        }