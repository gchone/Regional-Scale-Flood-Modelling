# -*- coding: utf-8 -*-


from LargeScaleFloodMetaTools import *
import os

class WatershedScaleDEMprocessing(object):
    def __init__(self):
        self.label = "Watershed-scale DEM processing"
        self.description = ""
        self.canRunInBackground = True

    def getParameterInfo(self):
        param_poly = arcpy.Parameter(
            displayName="Polygons of the river network",
            name="poly",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        param_lines_toburn = arcpy.Parameter(
            displayName="River network for stream burning (lines)",
            name="lines_toburn",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        param_DEMavg = arcpy.Parameter(
            displayName="DEM raster, 10m resolution",
            name="DEMavg",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Input")
        param_riverlines = arcpy.Parameter(
            displayName="River network (lines)",
            name="riverlines",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        param_riverlinesmain = arcpy.Parameter(
            displayName="River network - main channels only (lines)",
            name="riverlinesmain",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")

        param_toburnfrompoly = arcpy.Parameter(
            displayName="Output: Mask raster from polygons",
            name="toburnfrompoly",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output")
        param_toburnfromlines = arcpy.Parameter(
            displayName="Output: Rasterized lines (for stream burning)",
            name="toburnfromlines",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output")
        param_burnedDEM = arcpy.Parameter(
            displayName="Output: Burned DEM raster",
            name="burnedDEM",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output")
        param_fillDEM = arcpy.Parameter(
            displayName="Output: Burned DEM raster",
            name="fillDEM",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output")
        param_flowdirDEM = arcpy.Parameter(
            displayName="Output: Flow direction raster",
            name="flowdirDEM",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output")
        param_flowaccDEM = arcpy.Parameter(
            displayName="Output: Flow accumulation raster",
            name="flowaccDEM",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Output")
        param_routes = arcpy.Parameter(
            displayName="Output: Rivers route feature class",
            name="routes",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")
        param_links = arcpy.Parameter(
            displayName="Output: Link table",
            name="links",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")
        param_routes_main = arcpy.Parameter(
            displayName="Output: Rivers route feature class (main channels only)",
            name="routes_main",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")
        param_main_links = arcpy.Parameter(
            displayName="Output: Link table (main channels only)",
            name="main_links",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")
        param_routeD8 = arcpy.Parameter(
            displayName="Output: Route D8 feature class (lines)",
            name="routeD8",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")
        param_linksD8 = arcpy.Parameter(
            displayName="Output: Link table",
            name="linksD8",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")
        param_ptsonD8 = arcpy.Parameter(
            displayName="Output: Point on route D8 feature class (lines)",
            name="ptsonD8",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")
        param_relatetable = arcpy.Parameter(
            displayName="Output: Relate table",
            name="relatetable",
            datatype="GPTableView",
            parameterType="Required",
            direction="Output")

        project_path = arcpy.env.workspace

        param_poly.filter.list = ["Polygon"]
        param_poly.value = os.path.join(project_path, "Geometry.gdb", "channelpoly")
        param_lines_toburn.filter.list = ["Polyline"]
        param_lines_toburn.value = os.path.join(project_path, "Geometry.gdb", "watershed_net")
        param_routes.filter.list = ["Polyline"]
        param_DEMavg.value = os.path.join(project_path, "10mDEMs.gdb", "lidar10m_avg")
        param_riverlines.filter.list = ["Polyline"]
        param_riverlines.value = os.path.join(project_path, "Geometry.gdb", "linear_net_d")
        param_riverlinesmain.filter.list = ["Polyline"]
        param_riverlinesmain.value = os.path.join(project_path, "Geometry.gdb", "linear_main_d")


        param_toburnfrompoly.value = os.path.join(project_path, "Mask.gdb", "frompoly")
        param_toburnfromlines.value = os.path.join(project_path, "10mDEMs.gdb", "net_lines")
        param_burnedDEM.value = os.path.join(project_path, "10mDEMs.gdb", "lidar10m_burn")
        param_fillDEM.value = os.path.join(project_path, "10mDEMs.gdb", "lidar10m_fill")
        param_flowdirDEM.value = os.path.join(project_path, "10mDEMs.gdb", "lidar10m_fd")
        param_flowaccDEM.value = os.path.join(project_path, "10mDEMs.gdb", "lidar10m_facc")
        param_routes.value = os.path.join(project_path, "Geometry.gdb", "routes")
        param_links.value = os.path.join(project_path, "Geometry.gdb", "routes_links")
        param_routes_main.value = os.path.join(project_path, "Geometry.gdb", "routes_main")
        param_main_links.value = os.path.join(project_path, "Geometry.gdb", "routes_main_links")
        param_routeD8.value = os.path.join(project_path, "Geometry.gdb", "routesD8")
        param_linksD8.value = os.path.join(project_path, "Geometry.gdb", "links")
        param_ptsonD8.value = os.path.join(project_path, "Geometry.gdb", "pathpointsD8")
        param_relatetable.value = os.path.join(project_path, "Geometry.gdb", "fd_net_relatetable")

        params = [param_poly, param_lines_toburn, param_DEMavg, param_riverlines, param_riverlinesmain, param_toburnfrompoly,
                  param_toburnfromlines, param_burnedDEM, param_fillDEM, param_flowdirDEM, param_flowaccDEM, param_routes,
                  param_links, param_routes_main, param_main_links, param_routeD8, param_linksD8, param_ptsonD8, param_relatetable]

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):

        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):

        streamspoly_toburn = parameters[0].valueAsText
        streams_toburn = parameters[1].valueAsText
        DEM = arcpy.Raster(parameters[2].valueAsText)
        rivernet = parameters[3].valueAsText
        rivernet_main = parameters[4].valueAsText
        toburn_frompoly = parameters[5].valueAsText
        toburn_fromlines = parameters[6].valueAsText
        s_burned = parameters[7].valueAsText
        s_fill = parameters[8].valueAsText
        s_flow_dir = parameters[9].valueAsText
        s_flow_acc = parameters[10].valueAsText
        routes = parameters[11].valueAsText
        routes_links = parameters[12].valueAsText
        routes_main = parameters[13].valueAsText
        routes_main_links = parameters[14].valueAsText
        routeD8 = parameters[15].valueAsText
        linksD8 = parameters[16].valueAsText
        pathpointsD8 = parameters[17].valueAsText
        fd_net_relatetable = parameters[18].valueAsText

        execute_WatershedScaleDEMprocessing(DEM, streams_toburn, streamspoly_toburn, rivernet, rivernet_main,
                                            toburn_frompoly, toburn_fromlines,
                                            s_burned, s_fill, s_flow_dir, s_flow_acc, routes, routes_links, routes_main,
                                            routes_main_links,
                                            routeD8, linksD8, pathpointsD8, fd_net_relatetable,  "RID", "DownEnd", "Main", "Qorder", messages)
        return
