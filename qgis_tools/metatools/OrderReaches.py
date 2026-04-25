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

from metatools.LargeScaleFloodMetaTools import execute_order_reaches


class OrderReaches(QgsProcessingAlgorithm):
    ROUTES       = "ROUTES"
    LINKS        = "LINKS"
    RID_FIELD    = "RID_FIELD"
    R_FLOWACC    = "R_FLOWACC"
    ROUTED8      = "ROUTED8"
    LINKSD8      = "LINKSD8"
    PTSOND8      = "PTSOND8"
    RELATETABLE  = "RELATETABLE"
    OUTPUTFIELD  = "OUTPUTFIELD"
    ROUTES_OUT   = "ROUTES_OUT"

    def name(self):
        return "order_reaches"

    def displayName(self):
        return "Order reaches"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Metatools"

    def groupId(self):
        return "concordiariverlab_floodtools_metatools"

    def createInstance(self):
        return OrderReaches()

    def shortHelpString(self):
        return (
            "Order reaches\n\n"
            "Orders the reaches in the main route by flow accumulation. "
            "After running this tool, check that routes_main contains a field "
            "called \"Qorder\" with a distinct number for each attribute.\n\n"
            "Inputs:\n"
            "- routes_main: input route feature class (lines)\n"
            "- routes_main_links: link table\n"
            "- RID: RouteID field\n"
            "- lidar10m_facc: flow accumulation raster\n"
            "- routesD8: D8 route feature class (lines)\n"
            "- linksD8: D8 link table\n"
            "- pathpointsD8: points on D8 route table\n"
            "- fd_net_relatetable: relate table\n"
            "- Output field name (e.g. Qorder)\n\n"
            "Output:\n"
            "- routes_main with Qorder field added\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessing,
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterFeatureSource,
            QgsProcessingParameterField,
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterString,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.ROUTES,
                "routes_main",
                [QgsProcessing.TypeVectorLine],
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.LINKS,
                "routes_main_links",
                [QgsProcessing.TypeVector],
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.RID_FIELD,
                "RID (RouteID field)",
                parentLayerParameterName=self.ROUTES,
            )
        )

        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.R_FLOWACC,
                "lidar10m_facc (flow accumulation raster)",
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.ROUTED8,
                "routesD8",
                [QgsProcessing.TypeVectorLine],
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.LINKSD8,
                "linksD8",
                [QgsProcessing.TypeVector],
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.PTSOND8,
                "pathpointsD8",
                [QgsProcessing.TypeVector],
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.RELATETABLE,
                "fd_net_relatetable",
                [QgsProcessing.TypeVector],
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.OUTPUTFIELD,
                "Output field name",
                defaultValue="Qorder",
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.ROUTES_OUT,
                "routes_main",
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        routes      = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        links       = self.parameterAsSource(parameters, self.LINKS, context)
        rid_field   = self.parameterAsString(parameters, self.RID_FIELD, context)
        r_flowacc   = self.parameterAsRasterLayer(parameters, self.R_FLOWACC, context)
        routeD8     = self.parameterAsVectorLayer(parameters, self.ROUTED8, context)
        linksD8     = self.parameterAsSource(parameters, self.LINKSD8, context)
        ptsonD8     = self.parameterAsSource(parameters, self.PTSOND8, context)
        relatetable = self.parameterAsSource(parameters, self.RELATETABLE, context)
        outputfield = self.parameterAsString(parameters, self.OUTPUTFIELD, context)

        if routes is None:
            raise QgsProcessingException("routes_main layer is invalid")
        if links is None:
            raise QgsProcessingException("routes_main_links table is invalid")
        if r_flowacc is None:
            raise QgsProcessingException("Flow accumulation raster is invalid")
        if routeD8 is None:
            raise QgsProcessingException("routesD8 layer is invalid")
        if linksD8 is None:
            raise QgsProcessingException("linksD8 table is invalid")
        if ptsonD8 is None:
            raise QgsProcessingException("pathpointsD8 table is invalid")
        if relatetable is None:
            raise QgsProcessingException("fd_net_relatetable is invalid")
        if not outputfield:
            raise QgsProcessingException("Output field name is required")

        out_features = execute_order_reaches(
            routes=routes,
            links=links,
            rid_field=rid_field,
            r_flowacc=r_flowacc,
            routeD8=routeD8,
            linksD8=linksD8,
            ptsonD8=ptsonD8,
            relatetable=relatetable,
            outputfield=outputfield,
            feedback=feedback,
        )

        # Build output fields: all original routes_main fields + Qorder
        out_fields = QgsFields(routes.fields())
        if out_fields.indexOf(outputfield) == -1:
            out_fields.append(QgsField(outputfield, QMetaType.LongLong))

        (sink, sink_id) = self.parameterAsSink(
            parameters,
            self.ROUTES_OUT,
            context,
            out_fields,
            routes.wkbType(),
            routes.sourceCrs(),
        )

        for f in out_features:
            if feedback.isCanceled():
                break
            sink.addFeature(f, QgsFeatureSink.FastInsert)

        return {self.ROUTES_OUT: sink_id}