# -*- coding: utf-8 -*-
import arcpy
import numpy

from tree.TreeTools import *
from RelateNetworks import *
from LocatePointsAlongRoutes import *
from AssignPointToClosestPointOnRoute import *
from InterpolatePoints import *
from WSsmoothing import *
from D8toD4 import *
import ArcpyGarbageCollector as gc
from tree.TreeTools import *
from numpy.lib import recfunctions as rfn
import csv

def execute_WatershedScaleDEMprocessing(DEM, streams_toburn, streamspoly_toburn, rivernet, rivernet_main, toburn_frompoly, toburn_fromlines,
                                        s_burned, s_fill, s_flow_dir, s_flow_acc, routes, routes_links, routes_main, routes_main_links,
                                        routeD8, linksD8, pathpointsD8, fd_net_relatetable, RID_field, DownEnd_field, Main_field,
                                        Qorder_field, messages):
    ### Creates:
    # - Mask.gdb\frompoly
    # - 10mDEMs.gdb\net_lines
    # - 10mDEMs.gdb\lidar10m_burn
    # - 10mDEMs.gdb\lidar10m_fill
    # - 10mDEMs.gdb\lidar10m_fd
    # - 10mDEMs.gdb\lidar10m_facc
    # - Geometry.gdb\routes_main
    # - Geometry.gdb\routes_main_links
    # - Geometry.gdb\routes
    # - Geometry.gdb\routes_links
    # - Geometry.gdb\routesD8
    # - Geometry.gdb\linksD8
    # - Geometry.gdb\pathpointsD8
    # - Geometry.gdb\fd_net_relatetable

    arcpy.env.cellSize = DEM.catalogPath
    arcpy.env.snapRaster = DEM.catalogPath
    arcpy.env.extent = DEM.catalogPath
    arcpy.env.outputCoordinateSystem = DEM.catalogPath

    messages.addMessage("Stream-burning DEM..")

    arcpy.conversion.PolygonToRaster(streamspoly_toburn, arcpy.Describe(streamspoly_toburn).OIDFieldName, toburn_frompoly, cellsize = DEM)
    arcpy.conversion.PolylineToRaster(streams_toburn, arcpy.Describe(streams_toburn).OIDFieldName, toburn_fromlines, cellsize = DEM)

    burned_frompoly = arcpy.sa.Con( arcpy.sa.IsNull(toburn_frompoly), DEM, DEM-100)
    burned = arcpy.sa.Con( arcpy.sa.IsNull(toburn_fromlines), burned_frompoly, DEM-200)
    burned.save(s_burned)

    messages.addMessage("Hydraulic processing of DEM...")

    fill = arcpy.sa.Fill(burned)
    fill.save(s_fill)
    flow_dir = arcpy.sa.FlowDirection(fill)
    flow_dir.save(s_flow_dir)
    flow_acc = arcpy.sa.FlowAccumulation(flow_dir)
    flow_acc.save(s_flow_acc)

    messages.addMessage("Identifying river networks...")
    execute_CreateTreeFromShapefile(rivernet, routes, routes_links, RID_field, DownEnd_field,
                                    messages, Main_field)
    execute_CreateTreeFromShapefile(rivernet_main, routes_main, routes_main_links, RID_field, DownEnd_field,
                                    messages, None)

    execute_FlowDirNetwork(routes_main, routes_main_links, RID_field, flow_dir, routeD8, linksD8, pathpointsD8, fd_net_relatetable, messages)

    execute_OrderReaches(routes_main, routes_main_links, RID_field, flow_acc, routeD8, linksD8, pathpointsD8, fd_net_relatetable, Qorder_field, messages)


def execute_FlowDirNetwork(routes, links, RID_field, r_flow_dir, routeD8, linksD8, ptsonD8, relatetable, messages):
    fp = gc.CreateScratchName("fp", data_type="FeatureClass", workspace="in_memory")
    splits = gc.CreateScratchName("splits", data_type="FeatureClass", workspace="in_memory")
    execute_CreateFromPointsAndSplits(routes, links, RID_field, fp, splits)

    execute_TreeFromFlowDir(r_flow_dir, fp, routeD8, linksD8, RID_field, ptsonD8, messages, splits, 10000)

    execute_RelateNetworks(routes, RID_field, routeD8, RID_field, relatetable, messages)


def execute_OrderReaches(routes, links, RID_field, r_flowacc, routeD8, linksD8, ptsonD8, relatetable, outputfield, messages):

    D8_RID_field_in_relatetable = [f.name for f in arcpy.Describe(relatetable).fields][-2]

    # NB: extracting only the most points downstream points could have been avoided (as OrderTreeByFlowAcc use the most downstream point)
    # but maybe it's better that way as it avoids doing a costly convertion from table to shapefile and then ExtractMultiValuesToPoints
    QpointsD8 = gc.CreateScratchName("QptsD8", data_type="FeatureClass", workspace="in_memory")
    execute_LocateMostDownstreamPoints(routeD8, linksD8, RID_field, ptsonD8, "id", "RID", "dist", "X", "Y", QpointsD8)

    arcpy.sa.ExtractMultiValuesToPoints(QpointsD8, [[r_flowacc, "flowacc"]])

    arcpy.MakeFeatureLayer_management(QpointsD8, "qpts_lyr")
    arcpy.AddJoin_management("qpts_lyr", "id", ptsonD8, "id")
    arcpy.AddJoin_management("qpts_lyr", arcpy.Describe(ptsonD8).basename + ".RID", relatetable, D8_RID_field_in_relatetable)

    QpointsMain = gc.CreateScratchName("QptsMain", data_type="ArcInfoTable", workspace="in_memory")

    execute_LocatePointsAlongRoutes("qpts_lyr", arcpy.Describe(relatetable).basename + "." + RID_field, routes, RID_field, QpointsMain, 10000)

    execute_OrderTreeByFlowAcc(routes, links, RID_field, QpointsMain, "id", "RID", "MEAS", "flowacc", outputfield)

def execute_ExtractWaterSurface(routes, links, RID_field, order_field, routes_3m, RID_field_3m, relatetable, pts_table, X_field_pts, Y_field_pts, lidar3m_cor, DEMs_footprints, DEMs_field, pts_bathy, pts_bathy_ID_field, pts_bathy_RID_field, pts_bathy_dist_field, ouput_table, messages):
    # 2021-10-19 Assignation of elevation on points on routes (AssignPointToClosestPointOnRoute) done by "2-WAY CLOSEST" instead of "MEAN"
    #  relate table externalised, and inverted

    RID_field_in_relatetable = [f.name for f in arcpy.Describe(relatetable).fields][2]

    try:
        # Using ExtractMultiValuesToPoints on an event layer add a field in the input table
        # To prevent that, a copy must be previously made
        tmp_pts_table = gc.CreateScratchName("pts_table", data_type="ArcInfoTable", workspace=arcpy.env.scratchWorkspace)
        arcpy.management.Copy(pts_table, tmp_pts_table)
        arcpy.MakeXYEventLayer_management (tmp_pts_table, X_field_pts, Y_field_pts, "pts_layer", routes_3m)
        arcpy.sa.ExtractMultiValuesToPoints("pts_layer", [lidar3m_cor])

        arcpy.AddJoin_management("pts_layer", RID_field_3m, relatetable, RID_field_3m)

        pts_bathy_withws = gc.CreateScratchName("pts_withws", data_type="ArcInfoTable", workspace="in_memory")

        lidar3m_forws_basename = str(arcpy.Describe(lidar3m_cor).basename)

        execute_AssignPointToClosestPointOnRoute("pts_layer", [lidar3m_forws_basename],
                                                 routes, RID_field, pts_bathy, pts_bathy_RID_field, pts_bathy_dist_field,
                                                 [arcpy.Describe(relatetable).basename + "." + RID_field_in_relatetable],
                                                 [pts_bathy_RID_field], pts_bathy_withws, "2-WAY CLOSEST")
        pts_interpolated = gc.CreateScratchName("pts_interp", data_type="ArcInfoTable", workspace="in_memory")
        execute_InterpolatePoints(pts_bathy_withws, pts_bathy_ID_field, pts_bathy_RID_field, pts_bathy_dist_field, [lidar3m_forws_basename], pts_bathy, pts_bathy_ID_field, pts_bathy_RID_field, pts_bathy_dist_field, routes, links, RID_field, order_field, pts_interpolated)

        arcpy.MakeRouteEventLayer_lr(routes, RID_field, pts_interpolated, pts_bathy_RID_field + " POINT "+pts_bathy_dist_field, "interpolated_lyr")

        interpolated_withDEM = gc.CreateScratchName("interpDEM", data_type="FeatureClass", workspace="in_memory")
        arcpy.SpatialJoin_analysis("interpolated_lyr", DEMs_footprints, interpolated_withDEM)

        temp_outtable = gc.CreateScratchName("outtable", data_type="ArcInfoTable", workspace="in_memory")
        execute_WSprocessing(routes, links, RID_field, order_field, interpolated_withDEM, pts_bathy_ID_field, pts_bathy_RID_field, pts_bathy_dist_field, lidar3m_forws_basename, DEMs_field, temp_outtable, messages)

        arcpy.MakeRouteEventLayer_lr(routes, RID_field, temp_outtable, pts_bathy_RID_field + " POINT " + pts_bathy_dist_field, "D8pts_lyr")
        arcpy.CopyFeatures_management("D8pts_lyr", ouput_table)
    finally:
        gc.CleanAllTempFiles()

def execute_ExtractDischarges(routes_Atlas, links_Atlas, RID_field_Atlas, routes_AtlasD8, links_AtlasD8, RID_field_AtlasD8, pts_D8, fpoints_atlas, routesD8, routeD8_RID, routes_main, route_main_RID, relate_table, r_flowacc, outpoints_D8, outpoints_route, messages):

    try:
        matchatlas = gc.CreateScratchName("matchatlas", data_type="ArcInfoTable", workspace="in_memory")
        execute_CheckNetFitFromUpStream(routes_AtlasD8, links_AtlasD8, RID_field_AtlasD8, routes_Atlas, links_Atlas, RID_field_Atlas,
                                        fpoints_atlas, matchatlas, messages, "ENDS")

        QpointsD8 = gc.CreateScratchName("QptsD8", data_type="FeatureClass", workspace="in_memory")
        execute_LocateMostDownstreamPoints(routes_AtlasD8, links_AtlasD8, RID_field_AtlasD8, pts_D8, "id", "RID", "dist", "X", "Y", QpointsD8)

        Qpoints_subD8 = gc.CreateScratchName("QptsSub", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
        # points should be on the lines, but sometimes there's is a more or less 1cm shift. So a tolerance (10cm) was added
        arcpy.SpatialJoin_analysis(QpointsD8, routesD8, Qpoints_subD8, join_type="KEEP_COMMON", search_radius=0.1)
        arcpy.sa.ExtractMultiValuesToPoints(Qpoints_subD8, [[r_flowacc, "flowacc"]])

        arcpy.MakeFeatureLayer_management(Qpoints_subD8, "qpts_lyr")
        arcpy.AddJoin_management("qpts_lyr", "id", pts_D8, "id")
        arcpy.AddJoin_management("qpts_lyr", arcpy.Describe(pts_D8).basename + "." + RID_field_AtlasD8, matchatlas,
                                 RID_field_AtlasD8)

        D8_RID_field_in_relatetable = [f.name for f in arcpy.Describe(relate_table).fields][-2]
        arcpy.AddJoin_management("qpts_lyr", routeD8_RID, relate_table,
                                 D8_RID_field_in_relatetable)

        # Numpy array conversion to keep only the relevant fields (Main route RID and RID from the Atlas)
        fields_to_keep = [arcpy.Describe(relate_table).basename + "." + route_main_RID]
        fields_to_keep.append(arcpy.Describe(matchatlas).basename + ".MATCH_ID")
        fields_to_keep.append(arcpy.Describe("qpts_lyr").basename + ".flowacc")
        fields_to_keep.append(arcpy.Describe(matchatlas).basename + ".TYPO")
        fields_to_keep.append(arcpy.Describe(matchatlas).basename + ".CLOSEST")
        fields_to_keep.append(arcpy.Describe(matchatlas).basename + ".SCORE")
        fields_to_keep.append("SHAPE@XY")
        nparray = arcpy.da.FeatureClassToNumPyArray("qpts_lyr", fields_to_keep)

        nparray.dtype.names = [route_main_RID, "MATCH_ID", "Flowacc", "TYPO", "CLOSEST", "SCORE", "XY"]

        Qpoints_subD8_bis = gc.CreateScratchName("QptsSub", data_type="FeatureClass", workspace="in_memory")
        arcpy.da.NumPyArrayToFeatureClass(nparray, Qpoints_subD8_bis, "XY", arcpy.Describe(routesD8).spatialReference)

        arcpy.AddField_management(Qpoints_subD8_bis, "Drainage", "DOUBLE")
        arcpy.CalculateField_management(Qpoints_subD8_bis, "Drainage", str(r_flowacc.meanCellWidth) + "*" + str(
            r_flowacc.meanCellHeight) + "*!Flowacc!/1000000.", "PYTHON")

        arcpy.CopyFeatures_management(Qpoints_subD8_bis, outpoints_D8)

        res_table = gc.CreateScratchName("QptsTable", data_type="ArcInfoTable", workspace="in_memory")
        execute_LocatePointsAlongRoutes(Qpoints_subD8_bis, route_main_RID, routes_main, route_main_RID, res_table, 10000)

        arcpy.MakeRouteEventLayer_lr(routes_main, route_main_RID, res_table, route_main_RID + " POINT MEAS", "res_lyr")

        arcpy.CopyFeatures_management("res_lyr", outpoints_route)

    finally:
        gc.CleanAllTempFiles()


def execute_SpatializeQ(route_D8, RID_field_D8, D8pathpoints, relate_table, r_flowacc, routes, links, RID_field, Qorder_field, Qpoints, id_field_Qpoints, RID_Qpoints, dist_field_Qpoints, AtlasReach_field_Qpoints, targetpoints, id_field_target, RID_field_target, Distance_field_target, DEM_field_target, Qcsv_file, output_points, messages):

    # Extract Flow Acc along D8
    arcpy.MakeRouteEventLayer_lr(route_D8, RID_field_D8, D8pathpoints, RID_field_D8 + " POINT dist", "D8pts_lyr")
    D8pts = gc.CreateScratchName("targets", data_type="FeatureClass", workspace="in_memory")
    # I had a strange error when extracting the flow acc in a layer. Works if I use a Feature Class.... I don't know why
    arcpy.CopyFeatures_management("D8pts_lyr", D8pts)
    arcpy.sa.ExtractMultiValuesToPoints(D8pts, [[r_flowacc, "flowacc"]])
    arcpy.MakeFeatureLayer_management(D8pts, "D8pts_lyr2")
    D8_RID_field_in_relatetable = [f.name for f in arcpy.Describe(relate_table).fields][-2]
    arcpy.AddJoin_management("D8pts_lyr2", RID_field_D8, relate_table,
                             D8_RID_field_in_relatetable)

    # Join target points with the closest D8 point with the same RID
    targets_withFlowAcc = gc.CreateScratchName("targets", data_type="FeatureClass", workspace="in_memory")
    execute_AssignPointToClosestPointOnRoute("D8pts_lyr2",
                                             ["flowacc"], routes, RID_field, targetpoints, RID_field_target,
                                             Distance_field_target,
                                             [arcpy.Describe(relate_table).basename + "." + RID_field],
                                             [RID_field_target], targets_withFlowAcc, stat="CLOSEST")

    network = RiverNetwork()
    network.dict_attr_fields['id'] = RID_field
    network.dict_attr_fields['order'] = Qorder_field
    network.load_data(routes, links)

    Qcollection = Points_collection(network, "Qpts")
    Qcollection.dict_attr_fields['id'] = id_field_Qpoints
    Qcollection.dict_attr_fields['reach_id'] = RID_Qpoints
    Qcollection.dict_attr_fields['dist'] = dist_field_Qpoints
    Qcollection.dict_attr_fields['AtlasID'] = AtlasReach_field_Qpoints
    Qcollection.load_table(Qpoints)

    targetcollection = Points_collection(network, "target")
    targetcollection.dict_attr_fields['id'] = id_field_target
    targetcollection.dict_attr_fields['reach_id'] = RID_field_target
    targetcollection.dict_attr_fields['dist'] = Distance_field_target
    targetcollection.dict_attr_fields['DEM'] = DEM_field_target
    targetcollection.dict_attr_fields['flowacc'] = "flowacc"
    targetcollection.load_table(targets_withFlowAcc)

    # First browse: assign the closest downstream Q point at each target point
    for reach in network.browse_reaches_down_to_up():
        # Look for the closest downstream point in targetcollection
        down_point = None
        down_reach = reach
        while down_point is None and not down_reach.is_downstream_end(): # Looking for the closest downstream point fir the reach
            down_reach = down_reach.get_downstream_reach()
            down_point = down_reach.get_last_point(targetcollection)
        if reach.is_downstream_end() or not hasattr(down_point, "lastQpts"): # No downstream point (most downstream reach) or no Qpts point downstream
            lastQpts = None
        else:
            # discharge point associated with the closest downstream point in targetcollection
            lastQpts = down_point.lastQpts
        # Is there a discharge point on the current reach?
        for Qpts in reach.browse_points(Qcollection, orientation="DOWN_TO_UP"):
            if lastQpts is not None:
                if lastQpts.reach.id == reach.id:
                    min_dist = lastQpts.dist
                else:
                    min_dist = 0
                for targetpt in reach.browse_points(targetcollection, orientation="DOWN_TO_UP"):
                    if targetpt.dist >= min_dist and targetpt.dist < Qpts.dist:
                        targetpt.lastQpts = lastQpts
                        targetpt.QptsID = lastQpts.AtlasID
            lastQpts = Qpts
        if lastQpts is not None:
            # Assign the lastQpts to target points until the end of the reach
            if lastQpts.reach.id == reach.id:
                min_dist = lastQpts.dist
            else:
                min_dist = 0
            for targetpt in reach.browse_points(targetcollection, orientation="DOWN_TO_UP"):
                if targetpt.dist >= min_dist:
                    targetpt.lastQpts = lastQpts
                    targetpt.QptsID = lastQpts.AtlasID

    # First browse bis: assign the closest upstream Q point for points without downstream Q points
    for reach in network.browse_reaches_up_to_down(prioritize_reach_attribute="order", reverse=True):
        if reach.is_upstream_end():
            lastQpts = None
        for Qpts in reach.browse_points(Qcollection, orientation="UP_TO_DOWN"):
            lastQpts = Qpts
        if lastQpts is not None:
            for targetpt in reach.browse_points(targetcollection, orientation="UP_TO_DOWN"):
                if not hasattr(targetpt, "lastQpts"):
                    targetpt.lastQpts = lastQpts
                    targetpt.QptsID = lastQpts.AtlasID

    # First browse ter: check if every point has a Q points associated
    for reach in network.browse_reaches_down_to_up():
        for targetpt in reach.browse_points(targetcollection, orientation="DOWN_TO_UP"):
            if not hasattr(targetpt, "lastQpts"):
                messages.addErrorMessage("Points without an upstream or downstream discharge point on reach "+str(reach.id))
                raise AssertionError

    # Second browse: Extract the right Q LiDAR discharge and do the drainage area correction
    #  but first, the csv file is loaded into a dictionary
    #Qdata_array = genfromtxt(Qcsv_file, delimiter=',')
    Q_dict = {}
    with open(Qcsv_file, 'r') as csvfile:
        csvreader = csv.DictReader(csvfile)
        firstrowname = csvreader.fieldnames[0]
        for line in csvreader:
            Q_dict[line[firstrowname]]=line
    for reach in network.browse_reaches_down_to_up():
        for targetpt in reach.browse_points(targetcollection, orientation="DOWN_TO_UP"):
            try:
                Qlidar = float(Q_dict[str(targetpt.lastQpts.AtlasID)][str(targetpt.DEM)])
                targetpt.Qlidar = Qlidar * r_flowacc.meanCellWidth * r_flowacc.meanCellHeight *  targetpt.flowacc/1000000.
            except KeyError as e:
                messages.addErrorMessage("Missing line or column in the csv file: " + str(targetpt.DEM) + " / " + str(targetpt.lastQpts.AtlasID))

    # Originaly (commented below): Join the final results to the original target shapefile
    # Final thought: Better to leave this to be done manually
    targetcollection.add_SavedVariable("QptsID", "str", 20)
    targetcollection.add_SavedVariable("Qlidar", "float")

    #targets_withQ = gc.CreateScratchName("ttable", data_type="ArcInfoTable", workspace="in_memory")
    targetcollection.save_points(output_points)

    # # There was an issue with the Join. ArcGIS refused to mach the ID of the two tables. I don't get why.
    # # Resolved by using numpyarray
    # originalfields = [f.name for f in arcpy.Describe(targetpoints).fields]
    # original_nparray = arcpy.da.TableToNumPyArray(targetpoints, originalfields)
    # original_nparray = numpy.sort(original_nparray, order=id_field_target)
    # result_nparray = arcpy.da.TableToNumPyArray(targets_withQ, [id_field_target, "QptsID", "Qlidar"])
    # result_nparray = numpy.sort(result_nparray, order=id_field_target)
    # finalarray = rfn.merge_arrays([original_nparray, result_nparray[["QptsID", "Qlidar"]]], flatten=True)
    # if arcpy.env.overwriteOutput and arcpy.Exists(output_points):
    #     arcpy.Delete_management(output_points)
    # arcpy.da.NumPyArrayToTable(finalarray, output_points)

def execute_SpatializeQ_from_gauging_stations(routes_D8, links_D8, RID_field_D8, D8pathpoints, r_flowacc, Qpoints,
                                              id_field_Qpoints, name_field_Qpoints, drainage_area_field_Qpoints,
                                              Q_field, points_tol, Qcsv_file, DEM_footprints, DEM_id_field, beta_coef,
                                              relatetable, output_points, messages):
    # Two cases :
    # - either Q_field is a field in the Q points with the discharges to spatialize (DEM_footprints and Qcsv_file must be None).
    #   This is used to spatialize flood discharges
    # - Qcsv_file provides multiple discharges, and the right discharge to use is indicated by the DEM_footprints
    #   This is used to spatialize LiDAR discharges

    class Ref_point:
        def __init__(self, name, discharges, drainage_area, reach, dist):
            self.name = name
            self.discharges = discharges
            self.drainage_area = drainage_area
            self.reach = reach
            self.dist = dist

    # Extract Flow Acc along D8
    arcpy.MakeRouteEventLayer_lr(routes_D8, RID_field_D8, D8pathpoints, RID_field_D8 + " POINT dist", "D8pts_lyr")
    D8pts = gc.CreateScratchName("targets", data_type="FeatureClass", workspace="in_memory")
    # I had a strange error when extracting the flow acc in a layer. Works if I use a Feature Class.... I don't know why
    arcpy.CopyFeatures_management("D8pts_lyr", D8pts)
    arcpy.sa.ExtractMultiValuesToPoints(D8pts, [[r_flowacc, "flowacc"]])
    if Q_field is None:
        D8pts_withDEM = gc.CreateScratchName("D8ptsDEM", data_type="FeatureClass", workspace="in_memory")
        arcpy.SpatialJoin_analysis(D8pts, DEM_footprints, D8pts_withDEM)

    # Project points on the D8 network
    Qpoints_locatetable = gc.CreateScratchName("points", data_type="ArcInfoTable", workspace="in_memory")
    arcpy.LocateFeaturesAlongRoutes_lr(Qpoints, routes_D8, RID_field_D8, points_tol, Qpoints_locatetable,
                                       RID_field_D8 + " POINT MEAS")

    network = RiverNetwork()
    network.dict_attr_fields['id'] = RID_field_D8
    network.load_data(routes_D8, links_D8)

    Qcollection = Points_collection(network, "Qpts")
    Qcollection.dict_attr_fields['id'] = id_field_Qpoints
    Qcollection.dict_attr_fields['reach_id'] = RID_field_D8
    Qcollection.dict_attr_fields['dist'] = "MEAS"
    Qcollection.dict_attr_fields['name'] = name_field_Qpoints
    Qcollection.dict_attr_fields['drainage_area'] = drainage_area_field_Qpoints
    if Q_field is not None:
        Qcollection.dict_attr_fields['discharge'] = Q_field
    Qcollection.load_table(Qpoints_locatetable)

    targetcollection = Points_collection(network, "target")
    targetcollection.dict_attr_fields['id'] = "id"
    targetcollection.dict_attr_fields['reach_id'] = RID_field_D8
    targetcollection.dict_attr_fields['dist'] = "dist"
    targetcollection.dict_attr_fields['flowacc'] = "flowacc"
    if Q_field is None:
        targetcollection.dict_attr_fields['DEM'] = DEM_id_field
        targetcollection.load_table(D8pts_withDEM)
    else:
        targetcollection.load_table(D8pts)

    if Q_field is None:
        # Read the csv file, transpose it
        Q_dict = {} # dictionnary (key = name of gauging stations) with each entry being a dictionnary of discharges (key = code_dem)
        with open(Qcsv_file, 'r') as csvfile:
            csvreader = csv.DictReader(csvfile)
            for station in csvreader.fieldnames[1:]:
                Q_dict[station] = {}
            firstrowname = csvreader.fieldnames[0]
            discharges_list = []
            for line in csvreader:
                discharges_list.append(line[firstrowname])
                for station in csvreader.fieldnames[1:]:
                    if line[station] is not None and line[station] != '': # to avoid missing data
                        Q_dict[station][line[firstrowname]] = float(line[station])
        # For each gauging station point, assign its dictionnary of discharges
        for reach in network.browse_reaches_down_to_up():
            for Qpts in reach.browse_points(Qcollection, orientation="DOWN_TO_UP"):
                try:
                    Qpts.discharges = Q_dict[Qpts.name]
                except KeyError as e:
                    messages.addErrorMessage("Missing gauging station in the csv file: " + str(Qpts.name))
    else:
        # In the case of only discharges being a field in the gauging station file, format things the same way:
        Qpts.discharges = {Q_field: Qpts.discharge}
        discharges_list = [Q_field]
        for reach in network.browse_reaches_down_to_up():
            for Qpts in reach.browse_points(Qcollection, orientation="DOWN_TO_UP"):
                Qpts.discharges = {Q_field: Qpts.discharge}
            for targetpt in reach.browse_points(targetcollection, orientation="DOWN_TO_UP"):
                targetpt.DEM = Q_field

    # First browse: assign the upstream Q point(s) (in a list)
    # This is in addition done for each discharge, in case some stations have no data values in the csv file
    for discharge in discharges_list:
        for reach in network.browse_reaches_down_to_up():
            for targetpt in reach.browse_points(targetcollection, orientation="DOWN_TO_UP"):
                if not hasattr(targetpt, "upQpts"):
                    targetpt.upQpts = {}
                targetpt.upQpts[discharge] = [] # just to initiate the lists
                targetpt.downQpts = {}
        for reach in network.browse_reaches_up_to_down():
            if reach.is_upstream_end():
                lastQpts = None
            for Qpts in reach.browse_points(Qcollection, orientation="UP_TO_DOWN"):
                if lastQpts is not None:
                    if lastQpts.reach.id == reach.id:
                        max_dist = lastQpts.dist
                    else:
                        max_dist = None
                    for targetpt in reach.browse_points(targetcollection, orientation="UP_TO_DOWN"):
                        if (max_dist is None or targetpt.dist <= max_dist) and targetpt.dist > Qpts.dist:
                            if lastQpts.name not in [pt.name for pt in targetpt.upQpts[discharge]]:
                                targetpt.upQpts[discharge].append(lastQpts)
                lastQpts = Ref_point(Qpts.name, Qpts.discharges, Qpts.drainage_area, Qpts.reach, Qpts.dist)

            if lastQpts is not None:
                # Assign the lastQpts to target points until the end of the reach
                if lastQpts.reach.id == reach.id:
                    max_dist = lastQpts.dist
                else:
                    max_dist = None
                for targetpt in reach.browse_points(targetcollection, orientation="UP_TO_DOWN"):
                    if max_dist is None or targetpt.dist <= max_dist:
                        if lastQpts.name not in [pt.name for pt in targetpt.upQpts[discharge]]:
                            targetpt.upQpts[discharge].append(lastQpts)


    # Second browse: assign the closest downstream Q point at each target point
    # In the same browse, compute the discharges, by linear interpolation between each upstream/downstream pairs
    # If there are several upstream points, weight the results according to the upstream points drainage area
    # The final upstream point of a reach act as an input Q point for the upstream reaches
    for discharge in discharges_list:
        for reach in network.browse_reaches_down_to_up():

            ### First block : find the closest downstream Q point ###

            lastQpts = None
            if not reach.is_downstream_end():
                lastQpts = reach.get_downstream_reach().upstream_calculated_Q

            # Is there a discharge point on the current reach?
            for Qpts in reach.browse_points(Qcollection, orientation="DOWN_TO_UP"):
                if lastQpts is not None:
                    if lastQpts.reach.id == reach.id:
                        min_dist = lastQpts.dist
                    else:
                        min_dist = 0
                    for targetpt in reach.browse_points(targetcollection, orientation="DOWN_TO_UP"):
                        if targetpt.dist >= min_dist:
                            targetpt.downQpts[discharge] = lastQpts
                lastQpts = Ref_point(Qpts.name, Qpts.discharges, Qpts.drainage_area, Qpts.reach, Qpts.dist)

            if lastQpts is not None:
                # Assign the lastQpts to target points until the end of the reach
                if lastQpts.reach.id == reach.id:
                    min_dist = lastQpts.dist
                else:
                    min_dist = 0
                for targetpt in reach.browse_points(targetcollection, orientation="DOWN_TO_UP"):
                    if targetpt.dist >= min_dist:
                        targetpt.downQpts[discharge] = lastQpts


            ### Second block : compute the discharges ###

            for targetpt in reach.browse_points(targetcollection, orientation="DOWN_TO_UP"):
                targetpt.computedQLiDAR = -999

                localarea = targetpt.flowacc*r_flowacc.meanCellWidth*r_flowacc.meanCellHeight/1000000.
                if discharge not in targetpt.downQpts: # there is no downstream point
                    # A simple proportionnality of A**beta is done for each upstream point
                    for uppt in targetpt.upQpts[discharge]:
                        uppt.interpolatedQ = uppt.discharges[discharge]*(localarea/uppt.drainage_area)**beta_coef
                else:
                    # Linear interpolation of A**beta
                    for uppt in targetpt.upQpts[discharge]:
                        Q_from_down = (localarea ** beta_coef - uppt.drainage_area ** beta_coef) / (
                                    targetpt.downQpts[discharge].drainage_area ** beta_coef - uppt.drainage_area ** beta_coef)*targetpt.downQpts[discharge].discharges[discharge]
                        Q_from_up = (targetpt.downQpts[discharge].drainage_area ** beta_coef - localarea ** beta_coef) / (
                                targetpt.downQpts[discharge].drainage_area ** beta_coef - uppt.drainage_area ** beta_coef)*uppt.discharges[discharge]

                        uppt.interpolatedQ = Q_from_down + Q_from_up

                # weight the results according to the upstream points drainage area
                if len(targetpt.upQpts)>0:
                    targetpt.computedQLiDAR = 0
                    totalweight = sum([uppt.drainage_area for uppt in targetpt.upQpts[discharge]])
                    for uppt in targetpt.upQpts[discharge]:
                        targetpt.computedQLiDAR += uppt.interpolatedQ*uppt.drainage_area/totalweight
                else: # there is no upstream points
                    if discharge in targetpt.downQpts: # there is a downstream point
                        # A simple proportionnality of A**beta is done from the downstream point
                        targetpt.computedQLiDAR = targetpt.downQpts[discharge].discharges[discharge] * (localarea / targetpt.downQpts[discharge].drainage_area) ** beta_coef


            ### Third block: Convert the final upstream point into a Q input ###
            lastuppt = reach.get_last_point(targetcollection)
            reach.upstream_calculated_Q = Ref_point("uppt_reach"+str(reach.id), lastuppt.computedQLiDAR,
                                                    lastuppt.flowacc*r_flowacc.meanCellWidth*r_flowacc.meanCellHeight/1000000.,
                                                    reach, lastuppt.dist)

    if Q_field is None:
        targetcollection.add_SavedVariable("computedQLiDAR", "float")
    else:
        targetcollection.add_SavedVariable("computedQLiDAR", "float", None, Q_field)

    temp_outtable = gc.CreateScratchName("outtable", data_type="ArcInfoTable", workspace="in_memory")
    targetcollection.save_points(temp_outtable)
    arcpy.MakeRouteEventLayer_lr(routes_D8, RID_field_D8, temp_outtable, RID_field_D8 + " POINT dist", "D8pts_lyr")
    original_fields = [f.name for f in arcpy.Describe(temp_outtable).fields]
    if relatetable is not None:
        relatetable_fields = [f.name for f in arcpy.Describe(relatetable).fields]
        arcpy.management.AddJoin("D8pts_lyr", RID_field_D8, relatetable, relatetable_fields[2])
        arcpy.CopyFeatures_management("D8pts_lyr", output_points)
        aftercopy_fields = [f.name for f in arcpy.Describe(output_points).fields]
        # Clean field names
        for i, field in enumerate(original_fields):
            if i>0: # keep the first OID field name
                arcpy.AlterField_management(output_points, aftercopy_fields[i+1], field, field) # +1 because of the Shape field
        arcpy.AlterField_management(output_points, aftercopy_fields[len(original_fields)+3], "RID_D8", "RID_D8")
        arcpy.AlterField_management(output_points, aftercopy_fields[len(original_fields)+2], "RID_routesmain", "RID_routesmain")
    else:
        arcpy.CopyFeatures_management("D8pts_lyr", output_points)

def execute_LisfloodDataConversion(
    lidar10m_fd, lidar10m_fill, from_pts, workspace,
    routes_main, routes_main_links, routes_RID_field, routes_QOrder_field,
    bathy_pts, bathy_value_field, bathy_RID_field, bathy_dist_field, width_pts, width_value_field, width_RID_field, width_dist_field, d4fd, routesD4, linksD4,
        pathpointsD4, D4fd_net_relatetable, bathy_output_raster, width_output_raster, messages):
    # Create D4 network and spatialize bathymetry and width along this network
    # Outputs are:
    #   d4fd (Lisflood_inputs.gdb\d4fd): the D4 flow direction raster
    #   routesD4 (Lisflood_inputs.gdb\routesD4): the D4 river network
    #   linksD4 (Lisflood_inputs.gdb\linksD4): the D4 river network links
    #   pathpointsD4 (Lisflood_inputs.gdb\pathpointsD4): the D4 river network pathpoints
    #   D4fd_net_relatetable (Lisflood_inputs.gdb\D4fd_net_relatetable): the D4 network relate table
    #   bathy_output_raster (Lisflood_inputs.gdb\bathy): raster of bathymetry values along the D4 network
    #   width_output_raster (Lisflood_inputs.gdb\width): raster of width values along the D4 network

    # Step 1: D4 flow direction
    messages.addMessage('Extracting D4 flow direction network...')
    with arcpy.EnvManager(scratchWorkspace=workspace):
        execute_D8toD4(lidar10m_fd, lidar10m_fill, from_pts, d4fd, messages, language="EN")

    d4fd = arcpy.Raster(d4fd)
    # Step 2: Flow Direction Network
    execute_FlowDirNetwork(routes_main, routes_main_links, routes_RID_field, d4fd, routesD4, linksD4, pathpointsD4, D4fd_net_relatetable, messages)

    # Step 3: Add Qorder field
    if routes_QOrder_field not in [f.name for f in arcpy.ListFields(routesD4)]:
        arcpy.AddField_management(routesD4, routes_QOrder_field, 'SHORT')

    # Step 4: Join D4fd_net_relatetable to routesD4, then join routes_main to routesD4
    routesD4_lyr = arcpy.MakeFeatureLayer_management(routesD4, "routesD4_lyr")

    relatetable_field = [f.name for f in arcpy.Describe(D4fd_net_relatetable).fields]
    arcpy.management.AddJoin("routesD4_lyr", routes_RID_field, D4fd_net_relatetable, relatetable_field[2])
    routesD4_mainRID = arcpy.Describe(D4fd_net_relatetable).basename + "." + relatetable_field[1]
    arcpy.management.AddJoin("routesD4_lyr", routesD4_mainRID, routes_main, routes_RID_field)

    # Step 5: Copy Qorder values
    arcpy.management.CalculateField("routesD4_lyr", routes_QOrder_field, '!'+ arcpy.Describe(routes_main).basename + "." + routes_QOrder_field +'!', 'PYTHON3')

    # Step 6: Bed elevation workflow
    messages.addMessage('Processing bathymetry...')
    arcpy.MakeRouteEventLayer_lr(routes_main, routes_RID_field, bathy_pts, bathy_RID_field + ' Point ' + bathy_dist_field, "bathy_on_mainroute")
    arcpy.AddJoin_management("bathy_on_mainroute", bathy_RID_field, D4fd_net_relatetable, routes_RID_field)
    bathy_on_D4 = gc.CreateScratchName("temp", data_type="FeatureClass", workspace="in_memory")
    execute_AssignPointToClosestPointOnRoute("bathy_on_mainroute", [bathy_value_field], routesD4, routes_RID_field,
                                             pathpointsD4, 'RID', 'dist',
                                             [arcpy.Describe(D4fd_net_relatetable).basename + "." + relatetable_field[2]], [routes_RID_field], bathy_on_D4, "MAX")

    bathy_final = gc.CreateScratchName("temp", data_type="FeatureClass", workspace="in_memory")
    execute_InterpolatePoints(bathy_on_D4, 'id', 'RID', 'dist', [bathy_value_field],
                              pathpointsD4, 'id', 'RID', 'dist', routesD4,
                              linksD4, routes_RID_field, routes_QOrder_field, bathy_final)
    bathy_final_events = gc.CreateScratchName("temp", data_type="FeatureClass", workspace="in_memory")
    arcpy.MakeRouteEventLayer_lr(routesD4, routes_RID_field, bathy_final, 'RID Point dist', bathy_final_events)

    with arcpy.EnvManager(snapRaster=lidar10m_fd):
        with arcpy.EnvManager(extent=lidar10m_fd):
            with arcpy.EnvManager(outputCoordinateSystem=lidar10m_fd):
                arcpy.PointToRaster_conversion(bathy_final_events, bathy_value_field, bathy_output_raster, cell_assignment='MOST_FREQUENT', priority_field=None, cellsize=lidar10m_fd)

    # Step 7: Width workflow
    messages.addMessage('Processing width...')
    arcpy.MakeRouteEventLayer_lr(routes_main, routes_RID_field, width_pts, width_RID_field + ' Point ' + width_dist_field, "width_on_mainroute")
    arcpy.AddJoin_management("width_on_mainroute", width_RID_field, D4fd_net_relatetable, routes_RID_field)
    width_on_D4 = gc.CreateScratchName("temp", data_type="FeatureClass", workspace="in_memory")
    execute_AssignPointToClosestPointOnRoute("width_on_mainroute", [width_value_field], routesD4, routes_RID_field,
                                             pathpointsD4, 'RID', 'dist',
                                             [arcpy.Describe(D4fd_net_relatetable).basename + "." + relatetable_field[2]], [routes_RID_field], width_on_D4, "MEAN")

    width_final = gc.CreateScratchName("temp", data_type="FeatureClass", workspace="in_memory")
    execute_InterpolatePoints(width_on_D4, 'id', 'RID', 'dist', [width_value_field],
                              pathpointsD4, 'id', 'RID', 'dist', routesD4,
                              linksD4, routes_RID_field, routes_QOrder_field, width_final)
    width_final_events = gc.CreateScratchName("temp", data_type="FeatureClass", workspace="in_memory")
    arcpy.MakeRouteEventLayer_lr(routesD4, routes_RID_field, width_final, 'RID Point dist', width_final_events)

    with arcpy.EnvManager(snapRaster=lidar10m_fd):
        with arcpy.EnvManager(extent=lidar10m_fd):
            with arcpy.EnvManager(outputCoordinateSystem=lidar10m_fd):
                arcpy.PointToRaster_conversion(width_final_events, width_value_field, width_output_raster, cell_assignment='MOST_FREQUENT', priority_field=None, cellsize=lidar10m_fd)

