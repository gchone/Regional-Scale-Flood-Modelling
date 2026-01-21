# -*- coding: utf-8 -*-


import arcpy
from tree.TreeTools import *
from RelateNetworks import *
from WidthAssessment import *
from WSsmoothing import *
from AssignPointToClosestPointOnRoute import *
from InterpolatePoints import *
from ChannelCorrection import *
from BedAssessmentDirectLinearNet import *
#from BedAssessmentLinearNet import *
from Simple1Dhydraulic import *
from AnchorBathy import *

from LargeScaleFloodMetaTools import *

class Messages():
    def addErrorMessage(self, text):
        print (text)

    def addWarningMessage(self, text):
        print (text)

    def addMessage(self, text):
        print (text)




if __name__ == "__main__":
    arcpy.CheckOutExtension("Spatial")
    arcpy.env.overwriteOutput = True
    #arcpy.env.scratchWorkspace = r"E:\InfoCrue\tmp"
    arcpy.env.scratchWorkspace = r"E:\InfoCrue\Chaudiere\TestLinearRef\test.gdb"

    messages = Messages()

    # Create the river network
    shape = r"E:\InfoCrue\Chaudiere\TestLinearRef2\New File Geodatabase.gdb\linear_net_d"
    routes = r"E:\InfoCrue\Chaudiere\TestLinearRef2\New File Geodatabase.gdb\routes"
    links = r"E:\InfoCrue\Chaudiere\TestLinearRef2\New File Geodatabase.gdb\routes_links"
    #execute_CreateTreeFromShapefile(shape, routes, links, "RID", "DownEnd", messages, "Main")
    shape_main = r"E:\InfoCrue\Chaudiere\TestLinearRef2\New File Geodatabase.gdb\linear_main_d"
    routes_main = r"E:\InfoCrue\Chaudiere\TestLinearRef2\New File Geodatabase.gdb\routes_main"
    links_main = r"E:\InfoCrue\Chaudiere\TestLinearRef2\New File Geodatabase.gdb\routes_main_links"
    #execute_CreateTreeFromShapefile(shape_main, routes_main, links_main, "RID", "DownEnd", messages)


    flowdir = arcpy.Raster(
        r"E:\InfoCrue\Chaudiere\TestLinearRef2\DEMs.gdb\DEM10m_avg_flowdir")

    routesD8 = r"E:\InfoCrue\Chaudiere\TestLinearRef2\New File Geodatabase.gdb\routeD8"
    linksD8 =r"E:\InfoCrue\Chaudiere\TestLinearRef2\New File Geodatabase.gdb\linksD8"
    pathpoints = r"E:\InfoCrue\Chaudiere\TestLinearRef2\New File Geodatabase.gdb\pathpointsD8"
    basicnet_to_D8_relatetable = r"E:\InfoCrue\Chaudiere\TestLinearRef2\New File Geodatabase.gdb\net_to_D8_relationshiptable5"
    #execute_FlowDirNetwork(routes_main, links_main, "RID", flowdir, routesD8, linksD8, pathpoints, basicnet_to_D8_relatetable, messages)

    flowacc = arcpy.Raster(
        r"E:\InfoCrue\Chaudiere\TestLinearRef2\DEMs.gdb\DEM10m_avg_flowacc")
    #execute_OrderReaches(routes_main, links_main, "RID", flowacc, routesD8, linksD8, pathpoints, basicnet_to_D8_relatetable, "Qorder", messages)


    ### Water Surface ####
    lidar3m = arcpy.Raster(r"E:\InfoCrue\Chaudiere\TestLinearRef2\DEMs.gdb\dem3mmin_br_cor")
    channel = r"E:\InfoCrue\Chaudiere\TestLinearRef2\New File Geodatabase.gdb\poly_chenal"
    ends = r"E:\InfoCrue\Chaudiere\TestLinearRef2\WaterSurface.gdb\Ends"
    linear = r"E:\InfoCrue\Chaudiere\TestLinearRef2\New File Geodatabase.gdb\linear_main_d"
    DEMs_footprints = r"E:\InfoCrue\Chaudiere\TestLinearRef2\New File Geodatabase.gdb\Limites_merge"
    DEMs_footprints_id = "ORIG_FID"
    ws3m = r"E:\InfoCrue\Chaudiere\TestLinearRef2\WaterSurface.gdb\DEM3m_forws"
    #execute_ChannelCorrection(lidar3m, ends, channel, linear, DEMs_footprints, ws3m, messages)

    fpoints = r"E:\InfoCrue\Chaudiere\TestLinearRef2\New File Geodatabase.gdb\from_points"
    splits = r"E:\InfoCrue\Chaudiere\TestLinearRef2\New File Geodatabase.gdb\splits"
    #execute_CreateFromPointsAndSplits(routes_main, links_main, "RID", fpoints, splits)

    flowdir_ws3m = arcpy.Raster(
        r"E:\InfoCrue\Chaudiere\TestLinearRef2\WaterSurface.gdb\dem3m_forws_flowdir")
    routesD8_ws3m = r"E:\InfoCrue\Chaudiere\TestLinearRef2\WaterSurface.gdb\DEM3m_routeD8"
    linksD8_ws3m = r"E:\InfoCrue\Chaudiere\TestLinearRef2\WaterSurface.gdb\DEM3m_linksD8"
    pathpoints_ws3m = r"E:\InfoCrue\Chaudiere\TestLinearRef2\WaterSurface.gdb\DEM3m_pathpointsD8"
    #execute_TreeFromFlowDir(flowdir_ws3m, fpoints, routesD8_ws3m, linksD8_ws3m, "RID", pathpoints_ws3m, messages)

    lidar3m_forws = arcpy.Raster(r"E:\InfoCrue\Chaudiere\TestLinearRef2\WaterSurface.gdb\dem3m_forws")
    #bathy_datapts = bathy_datapts

    # execute_ExtractWaterSurface(routes_main, links_main, "RID", "Qorder", routesD8_ws3m, "RID", pathpoints_ws3m, "X", "Y",
    #                            lidar3m, lidar3m_forws, 5, DEMs_footprints, DEMs_footprints_id, bathy_datapts, messages)



    ### Discharge ###
    atlas = r"E:\InfoCrue\Chaudiere\TestLinearRef2\Discharge\Discharge.gdb\Atlas_full2_corr"
    route_atlas = r"E:\InfoCrue\Chaudiere\TestLinearRef2\Discharge.gdb\Atlas_routes2"
    links_atlas = r"E:\InfoCrue\Chaudiere\TestLinearRef2\Discharge.gdb\Atlas_links2"
    #execute_CreateTreeFromShapefile(atlas, route_atlas, links_atlas, "RID", "DownEnd", messages)
    fpoints_atlas = r"E:\InfoCrue\Chaudiere\TestLinearRef2\Discharge.gdb\Atlas_fp2"
    splits_atlas = r"E:\InfoCrue\Chaudiere\TestLinearRef2\Discharge.gdb\Atlas_splits2"
    #execute_CreateFromPointsAndSplits(route_atlas, links_atlas, "RID", fpoints_atlas, splits_atlas)
    routesD8_atlas = r"E:\InfoCrue\Chaudiere\TestLinearRef2\Discharge.gdb\routeD8_atlas2"
    linksD8_atlas =r"E:\InfoCrue\Chaudiere\TestLinearRef2\Discharge.gdb\linksD8_atlas2"
    pathpoints_atlas = r"E:\InfoCrue\Chaudiere\TestLinearRef2\Discharge.gdb\pathpointsD8_atlas2"
    #execute_TreeFromFlowDir(flowdir, fpoints_atlas, routesD8_atlas, linksD8_atlas, "RID", pathpoints_atlas, messages, splits_atlas, 10000)

    Qpoints_match = r"E:\InfoCrue\Chaudiere\TestLinearRef2\Discharge.gdb\Qpoints_match"
    # execute_ExtractDischarges(route_atlas, links_atlas, "RID", routesD8_atlas, linksD8_atlas,
    #                               "RID", pathpoints_atlas, fpoints_atlas, routesD8, "RID", routes_main,
    #                               "RID", basicnet_to_D8_relatetable, flowacc, Qpoints_match, messages)

    Qpoints_match_atlas = r"E:\InfoCrue\Chaudiere\TestLinearRef2\Discharge.gdb\Qpoints_match_Atlas"
    Qcsv_file = r"E:\InfoCrue\Chaudiere\TestLinearRef2\qlidaratlas2020_qspec.csv"
    Qpoints_spatialized = r"E:\InfoCrue\Chaudiere\TestLinearRef2\Discharge.gdb\Final_Qpoints"
    # execute_SpatializeQ(routesD8, "RID", pathpoints, basicnet_to_D8_relatetable, flowacc, routes_main, links_main, "RID", Qpoints_match_atlas, "OBJECTID", "RID", "MEAS",
    #                         "IDTRONCON",
    #                         bathy_datapts, "ObjectID_1", "RID", "MEAS", "ORIG_FID",
    #                         Qcsv_file, Qpoints_spatialized, messages)

    #### Width assessment ####

    widthpts = r"E:\InfoCrue\Chaudiere\TestLinearRef2\Width.gdb\widthcalcpts"
    widthtransects = r"E:\InfoCrue\Chaudiere\TestLinearRef2\Width.gdb\widthtransects"
    #execute_largeurpartransect(routes, "RID", channel, None, 1000, 5, widthtransects, widthpts, messages)

    widthoutput = r"E:\InfoCrue\Chaudiere\TestLinearRef2\test.gdb\test_final_width_pts2"
    #execute_WidthPostProc(routes, "RID", "Main", routes_main, "RID", "Shape_Length", "Qorder", links_main, widthpts, "CSid", "RID", "Distance_m", "Largeur_m", Qpoints_spatialized, "OBJECTID_1", "MEAS", "RID", widthoutput, messages)

    #### Bathy assessment ####
    datapts = r"E:\InfoCrue\Chaudiere\TestLinearRef2\bathy.gdb\datapts_August21"
    bathyoutput = r"E:\InfoCrue\Chaudiere\TestLinearRef2\bathy.gdb\bathypts_highs2"
    #verif_output = r"E:\InfoCrue\Chaudiere\TestLinearRef2\bathy.gdb\verif_10cm_full2"
    execute_BedAssessment(routes_main, "RID", "Qorder", links_main, datapts, "OBJECTID_1", "RID", "MEAS", "Qlidar",
                      "Largeur_m", "zsmooth", "ORIG_FID", 0.03, bathyoutput, messages)
    bathyoutput_post = r"E:\InfoCrue\Chaudiere\AnchoredBathy\bathy.gdb\test_postanchor2"
    # execute_AnchorBathy(routes_main, "RID", "Qorder", links_main, bathyoutput, "OBJECTID_1",  "RID",
    #                     "MEAS",
    #                     "zsmooth", "Fr", "z", "median", bathyoutput_post, messages)

    #execute_Simple1Dhydraulic(routes_main, "RID", "Qorder", links_main, bathyoutput, "OBJECTID_1", "RID", "MEAS", "Qlidar",
    #                      "Largeur_m", "z", "ORIG_FID", 0.03, 0.0001, verif_output, messages)

    #### Transform results for Lisflood #####
    # flowdirD4 = arcpy.Raster(r"E:\InfoCrue\Chaudiere\TestLinearRef2\LisfloodInputs.gdb\DEM10m_D4fd")
    routesD4 = r"E:\InfoCrue\Chaudiere\TestLinearRef2\LisfloodInputs.gdb\routeD4"
    linksD4 =r"E:\InfoCrue\Chaudiere\TestLinearRef2\LisfloodInputs.gdb\linksD4"
    pathpointsD4 = r"E:\InfoCrue\Chaudiere\TestLinearRef2\LisfloodInputs.gdb\pathpointsD4"
    basicnet_to_D4_relatetable = r"E:\InfoCrue\Chaudiere\TestLinearRef2\LisfloodInputs.gdb\relatetableD4"
    # execute_FlowDirNetwork(routes_main, links_main, "RID", flowdirD4, routesD4, linksD4, pathpointsD4, basicnet_to_D4_relatetable, messages)

    # Export the bathymetry
    #arcpy.MakeRouteEventLayer_lr(routes_main, "RID", bathyoutput, "RID POINT MEAS", "bathy_lyr")
    #arcpy.AddJoin_management("bathy_lyr", "RID", basicnet_to_D4_relatetable, "RID")
    #bathy_onD4 = r"E:\InfoCrue\Chaudiere\TestLinearRef2\LisfloodInputs.gdb\bathy_10cm_n04_onD4"
    #execute_AssignPointToClosestPointOnRoute("bathy_lyr", arcpy.Describe(basicnet_to_D4_relatetable).basename+".RID_1", ["z"], routesD4, "RID", pathpointsD4, "RID", "dist", bathy_onD4, "MAX")
    #final_bathy_pts = r"E:\InfoCrue\Chaudiere\TestLinearRef2\LisfloodInputs.gdb\final_bathy_10cm_n04"
    #execute_InterpolatePoints(bathy_onD4, "id", "RID", "dist", ["z"], pathpointsD4, "id", "RID", "dist", routesD4, linksD4, "RID", "Qorder", final_bathy_pts)

    # Export the width
    # arcpy.MakeRouteEventLayer_lr(routes_main, "RID", widthoutput, "RID POINT MEAS", "width_lyr")
    # arcpy.AddJoin_management("width_lyr", "RID", basicnet_to_D4_relatetable, "RID")
    # width_onD4 = r"E:\InfoCrue\Chaudiere\TestLinearRef2\LisfloodInputs.gdb\width_onD4"
    # execute_AssignPointToClosestPointOnRoute("width_lyr", arcpy.Describe(basicnet_to_D4_relatetable).basename+".RID_1", ["Largeur_m"], routesD4, "RID", pathpointsD4, "RID", "dist", width_onD4, "MEAN")
    # final_width_pts = r"E:\InfoCrue\Chaudiere\TestLinearRef2\LisfloodInputs.gdb\final_width_pts"
    # execute_InterpolatePoints(width_onD4, "id", "RID", "dist", ["Largeur_m"], pathpointsD4, "id", "RID", "dist", routesD4, linksD4, "RID", "Qorder", final_width_pts)

