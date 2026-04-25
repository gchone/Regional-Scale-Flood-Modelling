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
)
from qgis.PyQt.QtCore import QMetaType

sys.path.append(str(Path(__file__).resolve().parents[1]))

from tree_qgis.TreeTools import create_from_points_and_splits


class CreateFromPointsAndSplits(QgsProcessingAlgorithm):

    ROUTES = "ROUTES"
    LINKS = "LINKS"
    RID_FIELD = "RID_FIELD"
    FROM_POINTS = "FROM_POINTS"
    SPLITS = "SPLITS"

    def name(self):
        return "create_from_points_and_splits"

    def displayName(self):
        return "Create from points and split points"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return CreateFromPointsAndSplits()

    def shortHelpString(self):
        return (
            "Create from points and split points\n\n"
            "Classifies each reach's upstream endpoint as a from-point (headwater) "
            "or split-point (single upstream neighbour), for use as seeds in the "
            "flow direction network tracing step.\n\n"
            "Inputs:\n"
            "- Routes main: oriented route network (e.g. routes_main)\n"
            "- Links table: DownID/UpID link table (e.g. routes_main_links)\n"
            "- RouteID field: RID\n\n"
            "Outputs:\n"
            "- from_pts: headwater upstream endpoints with RID attribute\n"
            "- splits: single-upstream-neighbour endpoints (should be empty for routes_main)\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessing,
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES,
            "Routes main (routes_main)",
            [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.LINKS,
            "Links table (routes_main_links)",
            [QgsProcessing.TypeVector],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.RID_FIELD,
            "RouteID field",
            parentLayerParameterName=self.ROUTES,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.FROM_POINTS,
            "from_pts",
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.SPLITS,
            "splits",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        routes = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        links = self.parameterAsVectorLayer(parameters, self.LINKS, context)
        rid_field = self.parameterAsString(parameters, self.RID_FIELD, context)

        if routes is None:
            raise QgsProcessingException("Input routes layer is invalid")
        if links is None:
            raise QgsProcessingException("Input links layer is invalid")

        fp_features, split_features = create_from_points_and_splits(
            routes=routes,
            links=links,
            rid_field=rid_field,
            links_up_field="UpID",
            links_down_field="DownID",
            feedback=feedback,
        )

        # from_pts sink — points with RID attribute
        fp_fields = QgsFields()
        fp_fields.append(QgsField(rid_field, QMetaType.LongLong))

        (fp_sink, fp_id) = self.parameterAsSink(
            parameters, self.FROM_POINTS, context,
            fp_fields,
            QgsWkbTypes.Point,
            routes.sourceCrs(),
        )
        for f in fp_features:
            if feedback.isCanceled():
                break
            fp_sink.addFeature(f, QgsFeatureSink.FastInsert)

        # splits sink — points with no attributes
        (splits_sink, splits_id) = self.parameterAsSink(
            parameters, self.SPLITS, context,
            QgsFields(),
            QgsWkbTypes.Point,
            routes.sourceCrs(),
        )
        for f in split_features:
            if feedback.isCanceled():
                break
            splits_sink.addFeature(f, QgsFeatureSink.FastInsert)

        return {
            self.FROM_POINTS: fp_id,
            self.SPLITS: splits_id,
        }