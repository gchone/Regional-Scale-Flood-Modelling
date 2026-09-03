import arcpy

import ArcGIStools
from ArcGIS_Messages import Messages
from ExtractDischarges import execute_ExtractDischarges


class ArcGIS_ExtractDischarges_Interface(object):
    def __init__(self):
        self.label = "Extract Discharges Tool"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_routes_Atlas = arcpy.Parameter(
            displayName="Atlas route feature class (lines)",
            name="routes_Atlas",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
        )
        param_links_Atlas = arcpy.Parameter(
            displayName="Atlas route feature class links",
            name="links_Atlas",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_RID_field_Atlas = arcpy.Parameter(
            displayName="Atlas RouteID field",
            name="Rid_field_Atlas",
            datatype="FIeld",
            parameterType="Required",
            direction="Input",
        )
        param_routes_AtlasD8 = arcpy.Parameter(
            displayName="Atlas D8 route feature class (lines)",
            name="routes_AtlasD8",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
        )
        param_links_AtlasD8 = arcpy.Parameter(
            displayName="Atlas D8 route feature class links",
            name="links_AtlasD8",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_RID_field_AtlasD8 = arcpy.Parameter(
            displayName="Atlas D8 RouteID field",
            name="RID_field_AtlasD8",
            datatype="FIeld",
            parameterType="Required",
            direction="Input",
        )
        param_pts_D8 = arcpy.Parameter(
            displayName="Points D8",
            name="pts_D8",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_fpoints_atlas = arcpy.Parameter(
            displayName="From Points corresponding to Atlas",
            name="fpoints_atlas",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_routesD8 = arcpy.Parameter(
            displayName="Input route D8 feature class (lines)",
            name="routesD8",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
        )
        param_routeD8_RID = arcpy.Parameter(
            displayName="RouteID field in routeD8",
            name="routeD8_RID",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_routes_main = arcpy.Parameter(
            displayName="Input main route feature class (lines)",
            name="routes_main",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
        )
        param_route_main_RID = arcpy.Parameter(
            displayName="RouteID field in main route",
            name="route_main_RID",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )
        param_relate_table = arcpy.Parameter(
            displayName="Relate table",
            name="relate_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input",
        )
        param_r_flowacc = arcpy.Parameter(
            displayName="Flow Accumulation raster",
            name="r_flowacc",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input",
        )
        param_outpoints_D8 = arcpy.Parameter(
            displayName="Points en D8 - Output points",
            name="outpoints",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output",
        )
        param_outpoints_routes = arcpy.Parameter(
            displayName="Points on routes - Output points",
            name="outpoints2",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output",
        )

        param_RID_field_Atlas.parameterDependencies = [param_routes_Atlas.name]
        param_RID_field_AtlasD8.parameterDependencies = [param_routes_AtlasD8.name]
        param_routeD8_RID.parameterDependencies = [param_routesD8.name]
        param_route_main_RID.parameterDependencies = [param_routes_main.name]

        return [
            param_routes_Atlas,
            param_links_Atlas,
            param_RID_field_Atlas,
            param_routes_AtlasD8,
            param_links_AtlasD8,
            param_RID_field_AtlasD8,
            param_pts_D8,
            param_fpoints_atlas,
            param_routesD8,
            param_routeD8_RID,
            param_routes_main,
            param_route_main_RID,
            param_relate_table,
            param_r_flowacc,
            param_outpoints_D8,
            param_outpoints_routes,
        ]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        del parameters
        return

    def updateMessages(self, parameters):
        del parameters
        return

    def execute(self, parameters, messages):
        execute_ExtractDischarges(
            parameters[0].valueAsText,
            parameters[1].valueAsText,
            parameters[2].valueAsText,
            parameters[3].valueAsText,
            parameters[4].valueAsText,
            parameters[5].valueAsText,
            parameters[6].valueAsText,
            parameters[7].valueAsText,
            parameters[8].valueAsText,
            parameters[9].valueAsText,
            parameters[10].valueAsText,
            parameters[11].valueAsText,
            parameters[12].valueAsText,
            arcpy.Raster(parameters[13].valueAsText),
            parameters[14].valueAsText,
            parameters[15].valueAsText,
            GIStools=ArcGIStools,
            messages=Messages(messages),
        )
        return
