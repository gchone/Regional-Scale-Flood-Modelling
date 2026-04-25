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

from tree_qgis.RiverNetwork import RiverNetwork, PointsCollection


class LocateMostDownstreamPoints(QgsProcessingAlgorithm):
    NETWORK_SHP        = "NETWORK_SHP"
    LINKS_TABLE        = "LINKS_TABLE"
    RID_FIELD          = "RID_FIELD"
    DATAPOINTS         = "DATAPOINTS"
    ID_FIELD_PTS       = "ID_FIELD_PTS"
    RID_FIELD_PTS      = "RID_FIELD_PTS"
    DISTANCE_FIELD_PTS = "DISTANCE_FIELD_PTS"
    X_FIELD_PTS        = "X_FIELD_PTS"
    Y_FIELD_PTS        = "Y_FIELD_PTS"
    OUTPUT_PTS         = "OUTPUT_PTS"

    def name(self):
        return "locate_most_downstream_points"

    def displayName(self):
        return "Locate most downstream points on network"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return LocateMostDownstreamPoints()

    def shortHelpString(self):
        return (
            "Locate most downstream points on network\n\n"
            "Creates an output point feature class with the most downstream "
            "point of each reach in a network. Used to sample raster values "
            "(e.g. flow accumulation) at the downstream end of each D8 reach.\n\n"
            "Inputs:\n"
            "- Network feature class (lines): e.g. routesD8\n"
            "- Link table: e.g. linksD8\n"
            "- RouteID field in the network feature class: RID\n"
            "- Flow direction pixels along flow path table: e.g. pathpointsD8\n"
            "- ID field name from flow path table: id\n"
            "- RouteID field name from flow path table: RID\n"
            "- Distance field name from flow path table: dist\n"
            "- X field name from flow path table: X\n"
            "- Y field name from flow path table: Y\n\n"
            "Output:\n"
            "- Output point feature class with one point per reach\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessing,
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterFeatureSource,
            QgsProcessingParameterField,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.NETWORK_SHP,
                "Network feature class (routesD8)",
                [QgsProcessing.TypeVectorLine],
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.LINKS_TABLE,
                "Link table (linksD8)",
                [QgsProcessing.TypeVector],
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.RID_FIELD,
                "RouteID field in the network feature class",
                parentLayerParameterName=self.NETWORK_SHP,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.DATAPOINTS,
                "Flow direction pixels along flow path table (pathpointsD8)",
                [QgsProcessing.TypeVector],
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.ID_FIELD_PTS,
                "ID field name from flow path table (id)",
                parentLayerParameterName=self.DATAPOINTS,
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.RID_FIELD_PTS,
                "RouteID field name from flow path table (RID)",
                parentLayerParameterName=self.DATAPOINTS,
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.DISTANCE_FIELD_PTS,
                "Distance field name from flow path table (dist)",
                parentLayerParameterName=self.DATAPOINTS,
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.X_FIELD_PTS,
                "X field name from flow path table",
                parentLayerParameterName=self.DATAPOINTS,
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.Y_FIELD_PTS,
                "Y field name from flow path table",
                parentLayerParameterName=self.DATAPOINTS,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_PTS,
                "Output point feature class",
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        network_shp        = self.parameterAsVectorLayer(parameters, self.NETWORK_SHP, context)
        links_table        = self.parameterAsSource(parameters, self.LINKS_TABLE, context)
        rid_field          = self.parameterAsString(parameters, self.RID_FIELD, context)
        datapoints         = self.parameterAsSource(parameters, self.DATAPOINTS, context)
        id_field_pts       = self.parameterAsString(parameters, self.ID_FIELD_PTS, context)
        rid_field_pts      = self.parameterAsString(parameters, self.RID_FIELD_PTS, context)
        distance_field_pts = self.parameterAsString(parameters, self.DISTANCE_FIELD_PTS, context)
        x_field_pts        = self.parameterAsString(parameters, self.X_FIELD_PTS, context)
        y_field_pts        = self.parameterAsString(parameters, self.Y_FIELD_PTS, context)

        if network_shp is None:
            raise QgsProcessingException("Network layer is invalid")
        if links_table is None:
            raise QgsProcessingException("Link table is invalid")
        if datapoints is None:
            raise QgsProcessingException("Flow path table is invalid")

        out_features = locate_most_downstream_points(
            network_shp=network_shp,
            links_table=links_table,
            rid_field=rid_field,
            datapoints=datapoints,
            id_field_pts=id_field_pts,
            rid_field_pts=rid_field_pts,
            distance_field_pts=distance_field_pts,
            x_field_pts=x_field_pts,
            y_field_pts=y_field_pts,
            feedback=feedback,
        )

        out_fields = QgsFields()
        out_fields.append(QgsField("id", QMetaType.LongLong))

        (sink, sink_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_PTS,
            context,
            out_fields,
            QgsWkbTypes.Point,
            network_shp.sourceCrs(),
        )

        for f in out_features:
            if feedback.isCanceled():
                break
            sink.addFeature(f, QgsFeatureSink.FastInsert)

        return {self.OUTPUT_PTS: sink_id}


# =============================================================================
# Core function
# =============================================================================

def locate_most_downstream_points(
    network_shp,
    links_table,
    rid_field,
    datapoints,
    id_field_pts,
    rid_field_pts,
    distance_field_pts,
    x_field_pts,
    y_field_pts,
    feedback=None,
):
    """
    For each reach in the network, find the most downstream point from the
    flow path table (smallest dist value) and return it as a point feature.

    Mirrors ArcGIS execute_LocateMostDownstreamPoints() from TreeTools.py.

    Args:
        network_shp        : QgsVectorLayer (lines) — e.g. routesD8
        links_table        : QgsFeatureSource — e.g. linksD8
        rid_field          : str — RouteID field in network_shp
        datapoints         : QgsFeatureSource — e.g. pathpointsD8
        id_field_pts       : str — ID field in datapoints (e.g. "id")
        rid_field_pts      : str — RID field in datapoints (e.g. "RID")
        distance_field_pts : str — dist field in datapoints (e.g. "dist")
        x_field_pts        : str — X field in datapoints (e.g. "X")
        y_field_pts        : str — Y field in datapoints (e.g. "Y")
        feedback           : QgsProcessingFeedback or None

    Returns:
        list of QgsFeature (Point) with field: id (LongLong)
    """
    if feedback:
        feedback.pushInfo("Building network for most downstream point extraction…")

    network = RiverNetwork()
    network.load_data(network_shp, links_table, rid_field=rid_field)

    collection = PointsCollection(network, "data")
    collection.dict_attr_fields["id"]       = id_field_pts
    collection.dict_attr_fields["reach_id"] = rid_field_pts
    collection.dict_attr_fields["dist"]     = distance_field_pts
    collection.dict_attr_fields["X"]        = x_field_pts
    collection.dict_attr_fields["Y"]        = y_field_pts
    collection.load_table(datapoints)

    if feedback:
        feedback.pushInfo(
            f"Extracting most downstream point for each of "
            f"{len(network._reaches)} reach(es)…"
        )

    out_fields = QgsFields()
    out_fields.append(QgsField("id", QMetaType.LongLong))

    out_features = []
    for reach in network.browse_reaches_down_to_up():
        if feedback and feedback.isCanceled():
            break

        pt = reach.get_first_point(collection)
        if pt is None:
            if feedback:
                feedback.pushWarning(
                    f"No points found for reach RID={reach.id} — skipping."
                )
            continue

        feat = QgsFeature(out_fields)
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(pt.X, pt.Y)))
        feat.setAttribute("id", pt.id)
        out_features.append(feat)

    if feedback:
        feedback.pushInfo(
            f"Located {len(out_features)} most downstream point(s)."
        )

    return out_features