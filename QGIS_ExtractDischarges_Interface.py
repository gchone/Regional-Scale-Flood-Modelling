from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

import QGIStools
from QGIS_Messages import Messages
from ExtractDischarges import execute_ExtractDischarges

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessing,
)


class QGIS_ExtractDischarges(QgsProcessingAlgorithm):
    ROUTES_ATLAS = "ROUTES_ATLAS"
    LINKS_ATLAS = "LINKS_ATLAS"
    RID_FIELD_ATLAS = "RID_FIELD_ATLAS"
    ROUTES_ATLAS_D8 = "ROUTES_ATLAS_D8"
    LINKS_ATLAS_D8 = "LINKS_ATLAS_D8"
    RID_FIELD_ATLAS_D8 = "RID_FIELD_ATLAS_D8"
    PTS_D8 = "PTS_D8"
    FPOINTS_ATLAS = "FPOINTS_ATLAS"
    ROUTES_D8 = "ROUTES_D8"
    ROUTE_D8_RID = "ROUTE_D8_RID"
    ROUTES_MAIN = "ROUTES_MAIN"
    ROUTE_MAIN_RID = "ROUTE_MAIN_RID"
    RELATE_TABLE = "RELATE_TABLE"
    R_FLOWACC = "R_FLOWACC"
    OUTPOINTS_D8 = "OUTPOINTS_D8"
    OUTPOINTS_ROUTES = "OUTPOINTS_ROUTES"

    def name(self):
        return "extract_discharges"

    def displayName(self):
        return "Extract discharges"

    def group(self):
        return "Large Scale Flood Modelling Toolbox - Detailed Tools"

    def groupId(self):
        return "large_scale_flood_modelling_toolbox_detailed_tools"

    def createInstance(self):
        return QGIS_ExtractDischarges()

    def shortHelpString(self):
        return (
            "Extract discharge-support points by matching the Atlas D8 network back to the Atlas routes, "
            "keeping the most-downstream D8 path point per reach, snapping it to the D8 route network, "
            "sampling flow accumulation, and materializing the resulting points onto the main routes."
        )

    def initAlgorithm(self, config=None):
        from qgis.core import (
            QgsProcessingParameterVectorLayer,
            QgsProcessingParameterFeatureSource,
            QgsProcessingParameterField,
            QgsProcessingParameterRasterLayer,
            QgsProcessingParameterFeatureSink,
        )

        self.addParameter(QgsProcessingParameterVectorLayer(self.ROUTES_ATLAS, "Atlas route feature class (lines)", [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.LINKS_ATLAS, "Atlas route feature class links", [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD_ATLAS, "Atlas RouteID field", parentLayerParameterName=self.ROUTES_ATLAS, defaultValue="RID"))
        self.addParameter(QgsProcessingParameterVectorLayer(self.ROUTES_ATLAS_D8, "Atlas D8 route feature class (lines)", [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.LINKS_ATLAS_D8, "Atlas D8 route feature class links", [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterField(self.RID_FIELD_ATLAS_D8, "Atlas D8 RouteID field", parentLayerParameterName=self.ROUTES_ATLAS_D8, defaultValue="RID"))
        self.addParameter(QgsProcessingParameterFeatureSource(self.PTS_D8, "Points D8", [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.FPOINTS_ATLAS, "From Points corresponding to Atlas", [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterVectorLayer(self.ROUTES_D8, "Input route D8 feature class (lines)", [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterField(self.ROUTE_D8_RID, "RouteID field in routeD8", parentLayerParameterName=self.ROUTES_D8, defaultValue="RID"))
        self.addParameter(QgsProcessingParameterVectorLayer(self.ROUTES_MAIN, "Input main route feature class (lines)", [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterField(self.ROUTE_MAIN_RID, "RouteID field in main route", parentLayerParameterName=self.ROUTES_MAIN, defaultValue="RID"))
        self.addParameter(QgsProcessingParameterFeatureSource(self.RELATE_TABLE, "Relate table", [QgsProcessing.TypeVector]))
        self.addParameter(QgsProcessingParameterRasterLayer(self.R_FLOWACC, "Flow Accumulation raster"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPOINTS_D8, "Points en D8 - Output points"))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPOINTS_ROUTES, "Points on routes - Output points"))

    def processAlgorithm(self, parameters, context, feedback):
        routes_atlas = self.parameterAsVectorLayer(parameters, self.ROUTES_ATLAS, context)
        links_atlas = self.parameterAsSource(parameters, self.LINKS_ATLAS, context)
        rid_field_atlas = self.parameterAsString(parameters, self.RID_FIELD_ATLAS, context)
        routes_atlas_d8 = self.parameterAsVectorLayer(parameters, self.ROUTES_ATLAS_D8, context)
        links_atlas_d8 = self.parameterAsSource(parameters, self.LINKS_ATLAS_D8, context)
        rid_field_atlas_d8 = self.parameterAsString(parameters, self.RID_FIELD_ATLAS_D8, context)
        pts_d8 = self.parameterAsSource(parameters, self.PTS_D8, context)
        fpoints_atlas = self.parameterAsSource(parameters, self.FPOINTS_ATLAS, context)
        routes_d8 = self.parameterAsVectorLayer(parameters, self.ROUTES_D8, context)
        route_d8_rid = self.parameterAsString(parameters, self.ROUTE_D8_RID, context)
        routes_main = self.parameterAsVectorLayer(parameters, self.ROUTES_MAIN, context)
        route_main_rid = self.parameterAsString(parameters, self.ROUTE_MAIN_RID, context)
        relate_table = self.parameterAsSource(parameters, self.RELATE_TABLE, context)
        r_flowacc = self.parameterAsRasterLayer(parameters, self.R_FLOWACC, context)
        outpoints_d8 = self.parameterAsOutputLayer(parameters, self.OUTPOINTS_D8, context)
        outpoints_routes = self.parameterAsOutputLayer(parameters, self.OUTPOINTS_ROUTES, context)

        if None in [routes_atlas, links_atlas, routes_atlas_d8, links_atlas_d8, pts_d8, fpoints_atlas, routes_d8, routes_main, relate_table, r_flowacc]:
            raise QgsProcessingException("One or more input layers are invalid")

        execute_ExtractDischarges(
            routes_atlas,
            links_atlas,
            rid_field_atlas,
            routes_atlas_d8,
            links_atlas_d8,
            rid_field_atlas_d8,
            pts_d8,
            fpoints_atlas,
            routes_d8,
            route_d8_rid,
            routes_main,
            route_main_rid,
            relate_table,
            r_flowacc,
            outpoints_d8,
            outpoints_routes,
            GIStools=QGIStools,
            messages=Messages(feedback),
        )
        return {
            self.OUTPOINTS_D8: outpoints_d8,
            self.OUTPOINTS_ROUTES: outpoints_routes,
        }


ExtractDischarges = QGIS_ExtractDischarges
