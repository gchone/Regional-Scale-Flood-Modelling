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
from qgis.PyQt.QtCore import QVariant, QMetaType

sys.path.append(str(Path(__file__).resolve().parents[1]))

from tree_qgis.TreeTools import create_network_from_fc

class CreateNetworkFromFC(QgsProcessingAlgorithm):
    RIVNET = "RIVNET"
    RID_FIELD = "RID_FIELD"
    DOWNSTREAM_FIELD = "DOWNSTREAM_FIELD"
    CHANNELTYPE_FIELD = "CHANNELTYPE_FIELD"
    ROUTE_SHAPEFILE = "ROUTE_SHAPEFILE"
    ROUTELINKS_TABLE = "ROUTELINKS_TABLE"

    def name(self):
        return "create_network_from_feature_class"

    def displayName(self):
        return "Create network from feature class"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return CreateNetworkFromFC()

    def shortHelpString(self):
        return (
            "Create network from feature class\n\n"
            "Creates a river network data structure from a line feature class, defined by a "
            "link table and a RouteID. Run twice: once for the network containing secondary "
            "branches and once for the main network.\n\n"
            "Inputs:\n"
            "- Input feature class (lines): line layer (e.g., linear_net_d / linear_main_d)\n"
            "- RouteID field: RID (RouteID)\n"
            "- Field identifying the most downstream reach: DownEnd (value = 1 for downstream end)\n"
            "- Field identifying the main or secondary channel (optional): Main "
            "(1 = main channel, 0 = secondary)\n\n"
            "Outputs:\n"
            "- routes_main: oriented network layer\n"
            "- routes_main_links: link table (DownRID → UpRID)\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessing,
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterField,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.RIVNET,
                "Input feature class (lines)",
                [QgsProcessing.TypeVectorLine],
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.RID_FIELD,
                "RouteID field",
                parentLayerParameterName=self.RIVNET,
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.DOWNSTREAM_FIELD,
                "Field identifying the most downstream reach",
                parentLayerParameterName=self.RIVNET,
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.CHANNELTYPE_FIELD,
                "Field identifying the main or secondary channel",
                parentLayerParameterName=self.RIVNET,
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.ROUTE_SHAPEFILE,
                "routes_main",
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.ROUTELINKS_TABLE,
                "routes_main_links",
            )
        )


    def processAlgorithm(self, parameters, context, feedback):
        rivernet = self.parameterAsVectorLayer(parameters, self.RIVNET, context)
        rid_field = self.parameterAsString(parameters, self.RID_FIELD, context)
        downstream_field = self.parameterAsString(parameters, self.DOWNSTREAM_FIELD, context)
        channeltype_field = self.parameterAsString(parameters, self.CHANNELTYPE_FIELD, context)

        if rivernet is None:
            raise QgsProcessingException("Input network layer is invalid")

        out_features, links_rows = create_network_from_fc(
            rivernet=rivernet,
            rid_field=rid_field,
            downstream_field=downstream_field,
            channeltype_field=channeltype_field if channeltype_field else None,
            feedback=feedback,
        )

        (network_sink, network_id) = self.parameterAsSink(
            parameters,
            self.ROUTE_SHAPEFILE,
            context,
            rivernet.fields(),
            rivernet.wkbType(),
            rivernet.sourceCrs(),
        )

        for f in out_features:
            if feedback.isCanceled():
                break
            network_sink.addFeature(f, QgsFeatureSink.FastInsert)

        link_fields = QgsFields()
        link_fields.append(QgsField("DownRID", QMetaType.LongLong))
        link_fields.append(QgsField("UpRID", QMetaType.LongLong))

        (links_sink, links_id) = self.parameterAsSink(
            parameters,
            self.ROUTELINKS_TABLE,
            context,
            link_fields,
            QgsWkbTypes.NoGeometry,
            rivernet.sourceCrs(),
        )

        for downrid, uprid in links_rows:
            if feedback.isCanceled():
                break
            lf = QgsFeature(link_fields)
            lf.setAttributes([int(downrid), int(uprid)])
            links_sink.addFeature(lf, QgsFeatureSink.FastInsert)

        return {
            self.ROUTE_SHAPEFILE: network_id,
            self.ROUTELINKS_TABLE: links_id,
        }
