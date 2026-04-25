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
)
from qgis.PyQt.QtCore import QMetaType

sys.path.append(str(Path(__file__).resolve().parents[1]))


class RelateNetworks(QgsProcessingAlgorithm):
    SHAPEFILE_A = "SHAPEFILE_A"
    RID_A       = "RID_A"
    SHAPEFILE_B = "SHAPEFILE_B"
    RID_B       = "RID_B"
    OUT_TABLE   = "OUT_TABLE"

    def name(self):
        return "relate_networks"

    def displayName(self):
        return "Relate network layers"

    def group(self):
        return "ConcordiaRiverLab-FloodTools: Modeling"

    def groupId(self):
        return "concordiariverlab_floodtools_modeling"

    def createInstance(self):
        return RelateNetworks()

    def shortHelpString(self):
        return (
            "Relate network layers\n\n"
            "Relates two route layers by intersecting them and keeping the RID "
            "combination with the highest number of intersection points (PART_COUNT). "
            "Run this to relate the original vector network to the D8-snapped network.\n\n"
            "Both layers must have the same number of features.\n\n"
            "Inputs:\n"
            "- First network layer (lines)\n"
            "- RouteID field in the first network layer\n"
            "- Second network layer (lines)\n"
            "- RouteID field in the second network layer\n\n"
            "Outputs:\n"
            "- Relate table (RID_main, RID_D8, PART_COUNT)\n"
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
                self.SHAPEFILE_A,
                "First network layer",
                [QgsProcessing.TypeVectorLine],
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.RID_A,
                "RouteID field in the first network layer",
                parentLayerParameterName=self.SHAPEFILE_A,
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.SHAPEFILE_B,
                "Second network layer",
                [QgsProcessing.TypeVectorLine],
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.RID_B,
                "RouteID field in the second network layer",
                parentLayerParameterName=self.SHAPEFILE_B,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUT_TABLE,
                "Relate table",
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        shapefile_a = self.parameterAsVectorLayer(parameters, self.SHAPEFILE_A, context)
        rid_a       = self.parameterAsString(parameters, self.RID_A, context)
        shapefile_b = self.parameterAsVectorLayer(parameters, self.SHAPEFILE_B, context)
        rid_b       = self.parameterAsString(parameters, self.RID_B, context)

        if shapefile_a is None:
            raise QgsProcessingException("First network layer is invalid")
        if shapefile_b is None:
            raise QgsProcessingException("Second network layer is invalid")
        if not rid_a:
            raise QgsProcessingException("RouteID field for first network is required")
        if not rid_b:
            raise QgsProcessingException("RouteID field for second network is required")

        relate_rows = relate_networks(
            shapefile_a=shapefile_a,
            rid_a=rid_a,
            shapefile_b=shapefile_b,
            rid_b=rid_b,
            feedback=feedback,
        )

        # Output: relate table (no geometry)
        out_fields = QgsFields()
        out_fields.append(QgsField("RID_main", QMetaType.LongLong))
        out_fields.append(QgsField("RID_D8", QMetaType.LongLong))
        out_fields.append(QgsField("PART_COUNT", QMetaType.LongLong))

        (out_sink, out_id) = self.parameterAsSink(
            parameters,
            self.OUT_TABLE,
            context,
            out_fields,
            QgsWkbTypes.NoGeometry,
            shapefile_a.sourceCrs(),
        )

        for rid_a_val, rid_b_val, part_count in relate_rows:
            if feedback.isCanceled():
                break
            f = QgsFeature(out_fields)
            f.setAttributes([int(rid_a_val), int(rid_b_val), int(part_count)])
            out_sink.addFeature(f, QgsFeatureSink.FastInsert)

        return {self.OUT_TABLE: out_id}


# =============================================================================
# Core function
# =============================================================================

def relate_networks(shapefile_a, rid_a, shapefile_b, rid_b, feedback=None, strict_count=True):
    """
    Relate two route line layers by intersecting them and keeping the RID
    combination with the highest number of intersection points per reach.

    Mirrors ArcGIS execute_RelateNetworks() but uses QgsVectorLayer objects
    and returns rows for the Processing wrapper to sink.

    Args:
        shapefile_a : QgsVectorLayer (lines) — first network (e.g. original routes)
        rid_a       : str — RouteID field name in shapefile_a
        shapefile_b : QgsVectorLayer (lines) — second network (e.g. D8 routes)
        rid_b       : str — RouteID field name in shapefile_b
        feedback    : QgsProcessingFeedback or None

    Returns:
        relate_rows : list of (rid_a_val, rid_b_val, part_count)
    """

    def warn(msg):
        if feedback:
            feedback.pushWarning(msg)
        else:
            print(f"WARNING: {msg}")

    # --- Feature count check ---
    count_a = shapefile_a.featureCount()
    count_b = shapefile_b.featureCount()

    if strict_count and count_a != count_b:
        raise Exception(
            f"The feature classes have different number of rows "
            f"(A={count_a}, B={count_b}). "
            f"This tool requires equal feature counts."
        )

    if feedback:
        feedback.pushInfo(f"Intersecting {count_a} features from each network…")

    # --- Intersect the two line layers at points ---
    # Build a dict: (rid_a_val, rid_b_val) -> part_count
    # by iterating features from A and checking intersection with B
    # using QgsGeometry.intersection()
    part_counts = {}

    # Index B features by their RID for fast lookup
    b_features = {int(f[rid_b]): f for f in shapefile_b.getFeatures() if f[rid_b] is not None}

    total = shapefile_a.featureCount()
    for i, feat_a in enumerate(shapefile_a.getFeatures()):
        if feedback and feedback.isCanceled():
            break
        if feedback and total:
            feedback.setProgress(int(100 * i / max(1, total)))

        rid_a_val = feat_a[rid_a]
        if rid_a_val is None:
            continue
        rid_a_val = int(rid_a_val)

        geom_a = feat_a.geometry()
        if geom_a is None or geom_a.isEmpty():
            continue

        for rid_b_val, feat_b in b_features.items():
            geom_b = feat_b.geometry()
            if geom_b is None or geom_b.isEmpty():
                continue

            if not geom_a.intersects(geom_b):
                continue

            intersection = geom_a.intersection(geom_b)
            if intersection is None or intersection.isEmpty():
                continue

            # Count intersection points (equivalent to ArcGIS PART_COUNT)
            if intersection.isMultipart():
                count = len(intersection.asMultiPoint())
            elif intersection.wkbType() == QgsWkbTypes.Point:
                count = 1
            else:
                # Lines or polygons touching — count as 1 shared segment
                count = 1

            key = (rid_a_val, rid_b_val)
            part_counts[key] = part_counts.get(key, 0) + count

    if feedback:
        feedback.pushInfo(f"Found {len(part_counts)} intersection pair(s). Filtering…")

    # --- Filter: keep highest PART_COUNT per RID_A ---
    # Group by rid_a_val
    from collections import defaultdict
    by_a = defaultdict(list)
    for (a, b), pc in part_counts.items():
        by_a[a].append((a, b, pc))

    filtered_a = []
    for a, rows in by_a.items():
        max_pc = max(r[2] for r in rows)
        filtered_a.extend(r for r in rows if r[2] == max_pc)

    # --- Filter: keep highest PART_COUNT per RID_B ---
    by_b = defaultdict(list)
    for row in filtered_a:
        by_b[row[1]].append(row)

    filtered_b = []
    for b, rows in by_b.items():
        max_pc = max(r[2] for r in rows)
        filtered_b.extend(r for r in rows if r[2] == max_pc)

    # --- One-to-one match check ---
    unique_a = {r[0] for r in filtered_b}
    unique_b = {r[1] for r in filtered_b}
    if len(unique_a) != len(filtered_b) or len(unique_b) != len(filtered_b):
        warn("Incorrect network match — relate table may contain duplicate RID combinations")

    if feedback:
        feedback.pushInfo(f"Relate table complete: {len(filtered_b)} row(s).")

    return filtered_b