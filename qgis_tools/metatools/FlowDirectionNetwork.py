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

# Add project root to path so Processing script can import project packages
sys.path.append(str(Path(__file__).resolve().parents[1]))

from metatools.LargeScaleFloodMetaTools import flow_direction_network


class FlowDirectionNetwork(QgsProcessingAlgorithm):
    ROUTES = "ROUTES"
    LINKS = "LINKS"
    RID_FIELD = "RID_FIELD"
    R_FLOW_DIR = "R_FLOW_DIR"
    ROUTED8 = "ROUTED8"
    LINKSD8 = "LINKSD8"
    PTSOND8 = "PTSOND8"
    RELATETABLE = "RELATETABLE"

    def name(self):
        return "flow_direction_network"

    def displayName(self):
        return "Flow direction network"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Metatools"

    def groupId(self):
        return "concordiariverlab_floodtools_metatools"

    def createInstance(self):
        return FlowDirectionNetwork()

    def shortHelpString(self):
        return (
            "Flow direction network\n\n"
            "Extracts a route following the D8 flow direction and relates the main route "
            "to the resulting route. Check that the output relate table contains both "
            "\"RID\" and \"RID_1\" fields.\n\n"
            "Inputs:\n"
            "- Input route feature class (lines)\n"
            "- Link table (UpID / DownID)\n"
            "- RouteID field\n"
            "- Flow direction raster\n\n"
            "Outputs:\n"
            "- Output route D8 (lines)\n"
            "- Link table (DownRID → UpRID)\n"
            "- Path points D8 table\n"
            "- Relate table (RID, RID_1, PART_COUNT)\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessing,
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterFeatureSource,
            QgsProcessingParameterField,
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.ROUTES,
                "Input route feature class (lines)",
                [QgsProcessing.TypeVectorLine],
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.LINKS,
                "Link table",
                [QgsProcessing.TypeVectorNoGeometry],
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.RID_FIELD,
                "RouteID field",
                parentLayerParameterName=self.ROUTES,
            )
        )

        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.R_FLOW_DIR,
                "Flow direction raster",
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.ROUTED8,
                "routesD8",
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.LINKSD8,
                "linksD8",
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.PTSOND8,
                "pathpointsD8",
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.RELATETABLE,
                "relatetable",
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        routes = self.parameterAsVectorLayer(parameters, self.ROUTES, context)
        links = self.parameterAsSource(parameters, self.LINKS, context)
        rid_field = self.parameterAsString(parameters, self.RID_FIELD, context)
        r_flow_dir = self.parameterAsRasterLayer(parameters, self.R_FLOW_DIR, context)

        if routes is None:
            raise QgsProcessingException("Input route layer is invalid")
        if links is None:
            raise QgsProcessingException("Input link table is invalid")
        if r_flow_dir is None:
            raise QgsProcessingException("Flow direction raster is invalid")
        if not rid_field:
            raise QgsProcessingException("RouteID field is required")

        # Run flow_direction_network from LargeScaleFloodMetaTools
        routed8_features, linksd8_rows, ptsond8_rows, relate_rows = flow_direction_network(
            routes=routes,
            links=links,
            rid_field=rid_field,
            r_flow_dir=r_flow_dir,
            feedback=feedback,
        )

        crs = routes.sourceCrs()

        # Output 1: routesD8 (lines)
        route_fields = QgsFields()
        route_fields.append(QgsField("RID", QMetaType.LongLong))
        route_fields.append(QgsField("Shape_Length", QMetaType.Double))
        route_fields.append(QgsField("ORIG_FID", QMetaType.LongLong))

        (route_sink, route_id) = self.parameterAsSink(
            parameters,
            self.ROUTED8,
            context,
            route_fields,
            QgsWkbTypes.MultiLineStringM,
            crs,
        )

        # Validate that returned features have the expected fields
        if routed8_features:
            expected = [f.name() for f in route_fields]
            first_feat = routed8_features[0]

            if not isinstance(first_feat, QgsFeature):
                raise QgsProcessingException("routed8_features must be QgsFeature objects")

            returned = [f.name() for f in first_feat.fields()]

            if expected != returned:
                raise QgsProcessingException(
                    "routesD8 field mismatch.\n"
                    f"Expected: {expected}\n"
                    f"Returned: {returned}"
                )
        else:
            feedback.pushWarning("No routed8 features were returned")

        for f in routed8_features:
            if feedback.isCanceled():
                break
            route_sink.addFeature(f, QgsFeatureSink.FastInsert)


        # Output 2: linksD8 (table)
        link_fields = QgsFields()
        link_fields.append(QgsField("id", QMetaType.LongLong))
        link_fields.append(QgsField("DownRID", QMetaType.LongLong))
        link_fields.append(QgsField("UpRID", QMetaType.LongLong))

        (links_sink, links_id) = self.parameterAsSink(
            parameters,
            self.LINKSD8,
            context,
            link_fields,
            QgsWkbTypes.NoGeometry,
            crs,
        )

        i = 1
        for downrid, uprid in linksd8_rows:
            if feedback.isCanceled():
                break
            lf = QgsFeature(link_fields)
            lf.setAttributes([i, int(downrid), int(uprid)])
            links_sink.addFeature(lf, QgsFeatureSink.FastInsert)
            i += 1

        # Output 3: pathpointsD8 (table)
        pt_fields = QgsFields()
        pt_fields.append(QgsField("id", QMetaType.LongLong))
        pt_fields.append(QgsField("RID", QMetaType.LongLong))
        pt_fields.append(QgsField("dist", QMetaType.Double))
        pt_fields.append(QgsField("offset", QMetaType.Double))
        pt_fields.append(QgsField("X", QMetaType.Double))
        pt_fields.append(QgsField("Y", QMetaType.Double))
        pt_fields.append(QgsField("row", QMetaType.LongLong))
        pt_fields.append(QgsField("col", QMetaType.LongLong))

        (pts_sink, pts_id) = self.parameterAsSink(
            parameters,
            self.PTSOND8,
            context,
            pt_fields,
            QgsWkbTypes.NoGeometry,
            crs,
        )

        for row in ptsond8_rows:
            if feedback.isCanceled():
                break
            f = QgsFeature(pt_fields)
            f.setAttributes([
                int(row[0]),   # id
                int(row[1]),   # RID
                float(row[2]), # dist
                float(row[3]), # offset
                float(row[4]), # X
                float(row[5]), # Y
                int(row[6]),   # row
                int(row[7]),   # col
            ])
            pts_sink.addFeature(f, QgsFeatureSink.FastInsert)

        # --- Output 4: relate table (table) ---
        relate_fields = QgsFields()
        relate_fields.append(QgsField("RID", QMetaType.LongLong))
        relate_fields.append(QgsField("RID_1", QMetaType.LongLong))
        relate_fields.append(QgsField("PART_COUNT", QMetaType.LongLong))

        (relate_sink, relate_id) = self.parameterAsSink(
            parameters,
            self.RELATETABLE,
            context,
            relate_fields,
            QgsWkbTypes.NoGeometry,
            crs,
        )

        for rid, rid_1, part_count in relate_rows:
            if feedback.isCanceled():
                break
            rf = QgsFeature(relate_fields)
            rf.setAttributes([int(rid), int(rid_1), int(part_count)])
            relate_sink.addFeature(rf, QgsFeatureSink.FastInsert)

        return {
            self.ROUTED8: route_id,
            self.LINKSD8: links_id,
            self.PTSOND8: pts_id,
            self.RELATETABLE: relate_id,
        }
