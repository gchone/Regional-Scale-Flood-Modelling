from pathlib import Path
import os
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from FlowDirectionForWS import execute_FlowDirectionForWS
import QGIStools
from QGIS_Messages import Messages

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)


class QGIS_FlowDirectionForWS(QgsProcessingAlgorithm):
    ROUTES_MAIN = "ROUTES_MAIN"
    DEM = "DEM"
    DEM_FOOTPRINTS = "DEM_FOOTPRINTS"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    def name(self):
        return "flowdirectionforws"

    def displayName(self):
        return "Flow Direction for Water Surface Assessment"

    def group(self):
        return "Large Scale Flood Modelling Toolbox"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox"

    def createInstance(self):
        return QGIS_FlowDirectionForWS()

    def shortHelpString(self):
        return (
            "Flow Direction for Water Surface Assessment\n\n"
            "For each DEM footprint, clips the DEM, builds ArcGIS-style 3 m walls with "
            "25 m route-exit openings, fills depressions, computes D8 flow direction, "
            "and writes one output raster per footprint."
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterFolderDestination,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ROUTES_MAIN,
            "Input main route feature class (lines)",
            [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.DEM,
            "DEM for water surface assessment",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.DEM_FOOTPRINTS,
            "DEM footprints feature class",
            [QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUTPUT_FOLDER,
            "Output folder",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        routes_main = self.parameterAsVectorLayer(parameters, self.ROUTES_MAIN, context)
        dem_layer = self.parameterAsRasterLayer(parameters, self.DEM, context)
        dem_footprints = self.parameterAsVectorLayer(parameters, self.DEM_FOOTPRINTS, context)
        output_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)

        if routes_main is None:
            raise QgsProcessingException("Input routes layer is invalid")
        if dem_layer is None:
            raise QgsProcessingException("Input DEM layer is invalid")
        if dem_footprints is None:
            raise QgsProcessingException("Input DEM footprints layer is invalid")

        os.makedirs(output_folder, exist_ok=True)
        execute_FlowDirectionForWS(
            routes_main,
            dem_layer,
            dem_footprints,
            output_folder,
            25,
            messages=Messages(feedback),
            GIStools=QGIStools,
        )
        return {self.OUTPUT_FOLDER: output_folder}


FlowDirectionForWS = QGIS_FlowDirectionForWS
