from pathlib import Path
import os
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from Tiling import execute_create_zones
import QGIStools
from QGIS_Messages import Messages

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)


class QGIS_Tiling(QgsProcessingAlgorithm):
    FLOWDIR = "FLOWDIR"
    LAKES = "LAKES"
    FROMPOINT = "FROMPOINT"
    DISTANCE = "DISTANCE"
    BUFFERW = "BUFFERW"
    OUT_FOLDER = "OUT_FOLDER"

    def name(self):
        return "tiling"

    def displayName(self):
        return "Tiling"

    def group(self):
        return "Large Scale Flood Modelling Toolbox"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox"

    def createInstance(self):
        return QGIS_Tiling()

    def shortHelpString(self):
        return (
            "Tiling\n\n"
            "Divides the study network into independent tiles for hydraulic simulations "
            "with LISFLOOD-FP. Segments the D8 flow path from each from-point by distance "
            "and lake boundaries. Creates tile polygons (polyzones) as rectangular envelopes "
            "around buffered segments, and source points at the upstream end of each tile.\n\n"
            "Inputs:\n"
            "- Flow direction: D8 flow direction raster (e.g. lidar10m_fd)\n"
            "- Lakes: lake polygon layer used as tile boundaries\n"
            "- From points: headwater from-points (e.g. from_pts)\n"
            "- Tiles length (m): target length of each tile along the flow path (default 15000)\n"
            "- Tiles minimum width (m): buffer distance for tile width (default 3000)\n"
            "- Tiles folder: output folder where polyzones and sourcepoints will be written\n\n"
            "Outputs:\n"
            "- polyzones.gpkg: rectangular tile polygons with GRID_CODE and Lake_ID fields\n"
            "- sourcepoints.gpkg: upstream source point for each tile\n"
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterFolderDestination,
            QgsProcessingParameterNumber,
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterVectorLayer,
        )

        self.addParameter(QgsProcessingParameterRasterLayer(
            self.FLOWDIR, "Flow direction (e.g. lidar10m_fd)"))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.LAKES, "Lakes",
            [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.FROMPOINT, "From points (e.g. from_pts)",
            [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterNumber(
            self.DISTANCE, "Tiles length (m)",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=15000))
        self.addParameter(QgsProcessingParameterNumber(
            self.BUFFERW, "Tiles minimum width (m)",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=3000))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUT_FOLDER, "Tiles folder"))

    def processAlgorithm(self, parameters, context, feedback):
        flowdir_layer = self.parameterAsRasterLayer(parameters, self.FLOWDIR, context)
        lakes_layer = self.parameterAsVectorLayer(parameters, self.LAKES, context)
        frompoint_layer = self.parameterAsVectorLayer(parameters, self.FROMPOINT, context)
        distance = self.parameterAsInt(parameters, self.DISTANCE, context)
        bufferw = self.parameterAsInt(parameters, self.BUFFERW, context)
        out_folder = self.parameterAsString(parameters, self.OUT_FOLDER, context)

        if flowdir_layer is None:
            raise QgsProcessingException("Flow direction layer is invalid")
        if lakes_layer is None:
            raise QgsProcessingException("Lakes layer is invalid")
        if frompoint_layer is None:
            raise QgsProcessingException("From points layer is invalid")

        os.makedirs(out_folder, exist_ok=True)
        execute_create_zones(
            flowdir_layer,
            lakes_layer,
            frompoint_layer,
            distance,
            bufferw,
            out_folder,
            QGIStools,
            Messages(feedback),
        )
        return {self.OUT_FOLDER: out_folder}
