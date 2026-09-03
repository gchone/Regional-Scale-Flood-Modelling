from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

import QGIStools
from QGIS_Messages import Messages
from LisfloodDataConversion import execute_LisfloodDataConversion

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)


class QGIS_LisfloodDataConversion(QgsProcessingAlgorithm):
    FLOWDIR = "FLOWDIR"
    FILLDEM = "FILLDEM"
    FROMPOINTS = "FROMPOINTS"
    WORKSPACE = "WORKSPACE"
    ROUTES_MAIN = "ROUTES_MAIN"
    ROUTES_MAIN_LINKS = "ROUTES_MAIN_LINKS"
    ROUTES_RID_FIELD = "ROUTES_RID_FIELD"
    ROUTES_QORDER_FIELD = "ROUTES_QORDER_FIELD"
    BATHY_PTS = "BATHY_PTS"
    BATHY_VALUE_FIELD = "BATHY_VALUE_FIELD"
    BATHY_RID_FIELD = "BATHY_RID_FIELD"
    BATHY_DIST_FIELD = "BATHY_DIST_FIELD"
    WIDTH_PTS = "WIDTH_PTS"
    WIDTH_VALUE_FIELD = "WIDTH_VALUE_FIELD"
    WIDTH_RID_FIELD = "WIDTH_RID_FIELD"
    WIDTH_DIST_FIELD = "WIDTH_DIST_FIELD"
    D4FD = "D4FD"
    ROUTES_D4 = "ROUTES_D4"
    LINKS_D4 = "LINKS_D4"
    PATHPOINTS_D4 = "PATHPOINTS_D4"
    RELATETABLE = "RELATETABLE"
    BATHY_RASTER = "BATHY_RASTER"
    WIDTH_RASTER = "WIDTH_RASTER"

    def name(self):
        return "lisflood_data_conversion"

    def displayName(self):
        return "D4 flow direction and Lisflood data conversion"

    def group(self):
        return "Large Scale Flood Modelling Toolbox"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox"

    def createInstance(self):
        return QGIS_LisfloodDataConversion()

    def shortHelpString(self):
        return (
            "Build the Lisflood D4 preparation stack in one run: derive the D4 flow-direction raster, "
            "trace the D4 network, copy Qorder from the main network, then project/interpolate "
            "bathymetry and width onto the D4 path points and rasterize both outputs onto the "
            "flow-direction grid."
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterFeatureSource,
            QgsProcessingParameterField,
            QgsProcessingParameterFile,
            QgsProcessingParameterRasterDestination,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterRasterLayer(self.FLOWDIR, "Flow Direction Raster"))
        self.addParameter(QgsProcessingParameterRasterLayer(self.FILLDEM, "Filled DEM"))
        self.addParameter(QgsProcessingParameterVectorLayer(self.FROMPOINTS, "From points", [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterFile(self.WORKSPACE, "Temp folder", behavior=QgsProcessingParameterFile.Folder))
        self.addParameter(QgsProcessingParameterVectorLayer(self.ROUTES_MAIN, "Main Routes", [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.ROUTES_MAIN_LINKS, "Main Route Links", [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterField(self.ROUTES_RID_FIELD, "Route ID Field", parentLayerParameterName=self.ROUTES_MAIN, defaultValue="RID"))
        self.addParameter(QgsProcessingParameterField(self.ROUTES_QORDER_FIELD, "Route QOrder Field", parentLayerParameterName=self.ROUTES_MAIN, defaultValue="Qorder"))
        self.addParameter(QgsProcessingParameterFeatureSource(self.BATHY_PTS, "Bathymetry Points", [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterField(self.BATHY_VALUE_FIELD, "Bathymetry Value Field", parentLayerParameterName=self.BATHY_PTS, defaultValue="z"))
        self.addParameter(QgsProcessingParameterField(self.BATHY_RID_FIELD, "Bathymetry RID Field", parentLayerParameterName=self.BATHY_PTS, defaultValue="RID"))
        self.addParameter(QgsProcessingParameterField(self.BATHY_DIST_FIELD, "Bathymetry Distance Field", parentLayerParameterName=self.BATHY_PTS, defaultValue="MEAS"))
        self.addParameter(QgsProcessingParameterFeatureSource(self.WIDTH_PTS, "Width Points", [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterField(self.WIDTH_VALUE_FIELD, "Width Value Field", parentLayerParameterName=self.WIDTH_PTS, defaultValue="Width_m"))
        self.addParameter(QgsProcessingParameterField(self.WIDTH_RID_FIELD, "Width RID Field", parentLayerParameterName=self.WIDTH_PTS, defaultValue="RID"))
        self.addParameter(QgsProcessingParameterField(self.WIDTH_DIST_FIELD, "Width Distance Field", parentLayerParameterName=self.WIDTH_PTS, defaultValue="MEAS"))
        self.addParameter(QgsProcessingParameterRasterDestination(self.D4FD, "D4 Flow Direction Raster"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.ROUTES_D4, "D4 Routes"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.LINKS_D4, "D4 Links"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.PATHPOINTS_D4, "D4 Path Points"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.RELATETABLE, "D4fd Net Relate Table"))
        self.addParameter(QgsProcessingParameterRasterDestination(self.BATHY_RASTER, "Output: Bathymetry raster for Lisflood"))
        self.addParameter(QgsProcessingParameterRasterDestination(self.WIDTH_RASTER, "Output: Width raster for Lisflood"))

    def processAlgorithm(self, parameters, context, feedback):
        lidar10m_fd = self.parameterAsRasterLayer(parameters, self.FLOWDIR, context)
        lidar10m_fill = self.parameterAsRasterLayer(parameters, self.FILLDEM, context)
        from_pts = self.parameterAsVectorLayer(parameters, self.FROMPOINTS, context)
        workspace = self.parameterAsFile(parameters, self.WORKSPACE, context)
        routes_main = self.parameterAsVectorLayer(parameters, self.ROUTES_MAIN, context)
        routes_main_links = self.parameterAsSource(parameters, self.ROUTES_MAIN_LINKS, context)
        routes_rid_field = self.parameterAsString(parameters, self.ROUTES_RID_FIELD, context)
        routes_qorder_field = self.parameterAsString(parameters, self.ROUTES_QORDER_FIELD, context)
        bathy_pts = self.parameterAsSource(parameters, self.BATHY_PTS, context)
        bathy_value_field = self.parameterAsString(parameters, self.BATHY_VALUE_FIELD, context)
        bathy_rid_field = self.parameterAsString(parameters, self.BATHY_RID_FIELD, context)
        bathy_dist_field = self.parameterAsString(parameters, self.BATHY_DIST_FIELD, context)
        width_pts = self.parameterAsSource(parameters, self.WIDTH_PTS, context)
        width_value_field = self.parameterAsString(parameters, self.WIDTH_VALUE_FIELD, context)
        width_rid_field = self.parameterAsString(parameters, self.WIDTH_RID_FIELD, context)
        width_dist_field = self.parameterAsString(parameters, self.WIDTH_DIST_FIELD, context)
        d4fd = self.parameterAsOutputLayer(parameters, self.D4FD, context)
        routes_d4 = self.parameterAsOutputLayer(parameters, self.ROUTES_D4, context)
        links_d4 = self.parameterAsOutputLayer(parameters, self.LINKS_D4, context)
        pathpoints_d4 = self.parameterAsOutputLayer(parameters, self.PATHPOINTS_D4, context)
        relate_table = self.parameterAsOutputLayer(parameters, self.RELATETABLE, context)
        bathy_output_raster = self.parameterAsOutputLayer(parameters, self.BATHY_RASTER, context)
        width_output_raster = self.parameterAsOutputLayer(parameters, self.WIDTH_RASTER, context)

        if None in [lidar10m_fd, lidar10m_fill, from_pts, routes_main, routes_main_links, bathy_pts, width_pts]:
            raise QgsProcessingException("One or more input layers are invalid")
        if workspace in [None, ""]:
            raise QgsProcessingException("Temp folder is invalid")

        execute_LisfloodDataConversion(
            lidar10m_fd,
            lidar10m_fill,
            from_pts,
            workspace,
            routes_main,
            routes_main_links,
            routes_rid_field,
            routes_qorder_field,
            bathy_pts,
            bathy_value_field,
            bathy_rid_field,
            bathy_dist_field,
            width_pts,
            width_value_field,
            width_rid_field,
            width_dist_field,
            d4fd,
            routes_d4,
            links_d4,
            pathpoints_d4,
            relate_table,
            bathy_output_raster,
            width_output_raster,
            messages=Messages(feedback),
            GIStools=QGIStools,
        )
        return {
            self.D4FD: d4fd,
            self.ROUTES_D4: routes_d4,
            self.LINKS_D4: links_d4,
            self.PATHPOINTS_D4: pathpoints_d4,
            self.RELATETABLE: relate_table,
            self.BATHY_RASTER: bathy_output_raster,
            self.WIDTH_RASTER: width_output_raster,
        }


LisfloodDataConversion = QGIS_LisfloodDataConversion
