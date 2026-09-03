from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

import QGIStools
from QGIS_Messages import Messages
from WatershedScaleDEMprocessing import execute_WatershedScaleDEMprocessing

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)


class QGIS_WatershedScaleDEMprocessing(QgsProcessingAlgorithm):
    POLY = "POLY"
    LINES_TOBURN = "LINES_TOBURN"
    DEMAVG = "DEMAVG"
    RIVERLINES = "RIVERLINES"
    RIVERLINESMAIN = "RIVERLINESMAIN"
    TOBURNFROMPOLY = "TOBURNFROMPOLY"
    TOBURNFROMLINES = "TOBURNFROMLINES"
    BURNEDDEM = "BURNEDDEM"
    FILLDEM = "FILLDEM"
    FLOWDIRDEM = "FLOWDIRDEM"
    FLOWACCDEM = "FLOWACCDEM"
    ROUTES = "ROUTES"
    LINKS = "LINKS"
    ROUTES_MAIN = "ROUTES_MAIN"
    MAIN_LINKS = "MAIN_LINKS"
    ROUTED8 = "ROUTED8"
    LINKSD8 = "LINKSD8"
    PTSOND8 = "PTSOND8"
    RELATETABLE = "RELATETABLE"

    def name(self):
        return "watershed_scale_dem_processing"

    def displayName(self):
        return "Watershed-scale DEM processing"

    def group(self):
        return "Large Scale Flood Modelling Toolbox"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox"

    def createInstance(self):
        return QGIS_WatershedScaleDEMprocessing()

    def shortHelpString(self):
        return (
            "Build the full watershed-scale DEM-processing stack in one run: rasterize stream-burning "
            "masks, burn/fill the DEM, compute D8 flow direction and flow accumulation, create the "
            "full and main-channel river networks, trace the D8 network, and assign Qorder."
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterRasterDestination,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(self.POLY, "Polygons of the river network", [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterVectorLayer(self.LINES_TOBURN, "River network for stream burning", [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterRasterLayer(self.DEMAVG, "DEM raster, 10m resolution"))
        self.addParameter(QgsProcessingParameterVectorLayer(self.RIVERLINES, "River network", [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterVectorLayer(self.RIVERLINESMAIN, "River network - main channels only", [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterRasterDestination(self.TOBURNFROMPOLY, "Output: Mask raster from polygons"))
        self.addParameter(QgsProcessingParameterRasterDestination(self.TOBURNFROMLINES, "Output: Rasterized lines (for stream burning)"))
        self.addParameter(QgsProcessingParameterRasterDestination(self.BURNEDDEM, "Output: Burned DEM raster"))
        self.addParameter(QgsProcessingParameterRasterDestination(self.FILLDEM, "Output: Filled DEM raster"))
        self.addParameter(QgsProcessingParameterRasterDestination(self.FLOWDIRDEM, "Output: Flow direction raster"))
        self.addParameter(QgsProcessingParameterRasterDestination(self.FLOWACCDEM, "Output: Flow accumulation raster"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.ROUTES, "Output: Rivers route feature class"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.LINKS, "Output: Link table"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.ROUTES_MAIN, "Output: Rivers route feature class (main channels only)"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.MAIN_LINKS, "Output: Link table (main channels only)"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.ROUTED8, "Output: Route D8 feature class"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.LINKSD8, "Output: Link table"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.PTSOND8, "Output: Point on route D8 feature class"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.RELATETABLE, "Output: Relate table"))

    def processAlgorithm(self, parameters, context, feedback):
        stream_polygons = self.parameterAsVectorLayer(parameters, self.POLY, context)
        streams_toburn = self.parameterAsVectorLayer(parameters, self.LINES_TOBURN, context)
        dem_layer = self.parameterAsRasterLayer(parameters, self.DEMAVG, context)
        rivernet = self.parameterAsVectorLayer(parameters, self.RIVERLINES, context)
        rivernet_main = self.parameterAsVectorLayer(parameters, self.RIVERLINESMAIN, context)

        outputs = {
            self.TOBURNFROMPOLY: self.parameterAsOutputLayer(parameters, self.TOBURNFROMPOLY, context),
            self.TOBURNFROMLINES: self.parameterAsOutputLayer(parameters, self.TOBURNFROMLINES, context),
            self.BURNEDDEM: self.parameterAsOutputLayer(parameters, self.BURNEDDEM, context),
            self.FILLDEM: self.parameterAsOutputLayer(parameters, self.FILLDEM, context),
            self.FLOWDIRDEM: self.parameterAsOutputLayer(parameters, self.FLOWDIRDEM, context),
            self.FLOWACCDEM: self.parameterAsOutputLayer(parameters, self.FLOWACCDEM, context),
            self.ROUTES: self.parameterAsOutputLayer(parameters, self.ROUTES, context),
            self.LINKS: self.parameterAsOutputLayer(parameters, self.LINKS, context),
            self.ROUTES_MAIN: self.parameterAsOutputLayer(parameters, self.ROUTES_MAIN, context),
            self.MAIN_LINKS: self.parameterAsOutputLayer(parameters, self.MAIN_LINKS, context),
            self.ROUTED8: self.parameterAsOutputLayer(parameters, self.ROUTED8, context),
            self.LINKSD8: self.parameterAsOutputLayer(parameters, self.LINKSD8, context),
            self.PTSOND8: self.parameterAsOutputLayer(parameters, self.PTSOND8, context),
            self.RELATETABLE: self.parameterAsOutputLayer(parameters, self.RELATETABLE, context),
        }

        if None in [stream_polygons, streams_toburn, dem_layer, rivernet, rivernet_main]:
            raise QgsProcessingException("One or more input layers are invalid")

        execute_WatershedScaleDEMprocessing(
            dem_layer,
            streams_toburn,
            stream_polygons,
            rivernet,
            rivernet_main,
            outputs[self.TOBURNFROMPOLY],
            outputs[self.TOBURNFROMLINES],
            outputs[self.BURNEDDEM],
            outputs[self.FILLDEM],
            outputs[self.FLOWDIRDEM],
            outputs[self.FLOWACCDEM],
            outputs[self.ROUTES],
            outputs[self.LINKS],
            outputs[self.ROUTES_MAIN],
            outputs[self.MAIN_LINKS],
            outputs[self.ROUTED8],
            outputs[self.LINKSD8],
            outputs[self.PTSOND8],
            outputs[self.RELATETABLE],
            "RID",
            "DownEnd",
            "Main",
            "Qorder",
            messages=Messages(feedback),
            GIStools=QGIStools,
        )
        return outputs


WatershedScaleDEMprocessing = QGIS_WatershedScaleDEMprocessing
