# -*- coding: utf-8 -*-

#####################################################
# Guénolé Choné
# Concordia University
# Geography, Planning and Environment Department
# guenole.chone@concordia.ca
#####################################################


import os
import arcpy

from tree.RiverNetwork import *
from tree.TreeTools import *

import SolverDirect
import Solver1Dnormal
from Simple1Dhydraulic import *


def execute_BedAssessment(route: object, route_RID_field: object, route_order_field: object, routelinks: object, points: object, points_IDfield: object,
                          points_RIDfield: object, points_distfield: object, points_Qfield: object, points_Wfield: object, points_WSfield: object,
                          points_DEMfield: object, manning: object, min_slope: object, output_pts: object, messages: object, method: object = "OVERSAMPLING", supercritical=False, max_delta_y = None) -> None:

    ## Two methods are available:
    # SIMPLE: Each cross-section is processed individually (no particular extra-process)
    # OVERSAMPLING: adding cross-sections when needed (default, depth parameter is not used)
    # 2-XS: using a two cross-sections downstream to compute the bed elevation for the first one

    rivernet = RiverNetwork()
    rivernet.dict_attr_fields['id'] = route_RID_field
    rivernet.dict_attr_fields['order'] = route_order_field
    rivernet.load_data(route, routelinks)

    points_coll = Points_collection(rivernet, "data")
    points_coll.dict_attr_fields['id'] = points_IDfield
    points_coll.dict_attr_fields['reach_id'] = points_RIDfield
    points_coll.dict_attr_fields['dist'] = points_distfield
    points_coll.dict_attr_fields['wslidar'] = points_WSfield
    points_coll.dict_attr_fields['Q'] = points_Qfield
    points_coll.dict_attr_fields['width'] = points_Wfield
    points_coll.dict_attr_fields['DEM'] = points_DEMfield
    points_coll.load_table(points)



    # First, prepare the list of cross-sections to use for each point. There are 3 cross-sections to add:
    # the point itself, its downstream point and its upstream one. Downstream point is only used if method = "2-XS".
    # Upstream point and current point are added in the first loop (browsing upstream to downstream) and downstream
    # point is added in the next loop (browsing downstream to upstream).
    # Also compute the slope for the most upstream points, where the manning's equation is used, and attribute the
    # manning value to each point

    # Computed distance from upstream point and add upstream and current points to listtosolve
    stopper = BrowsingStopper()
    done_reaches = []
    for reach in rivernet.browse_reaches_up_to_down(prioritize_reach_attribute="order", stopper=stopper):
        # Looking for the upstream datapoint
        if reach.is_upstream_end():
            prev_cs = None
        # no else: if it's not an upstream reach the prev_cs is already good
        if reach in done_reaches:
            stopper.break_generator = True
        else:
            for cs in reach.browse_points(points_coll, orientation="UP_TO_DOWN"):
                cs.listtosolve = [] # List of cross-sections to use for the hydraulic computation
                if prev_cs != None:
                    if cs.reach == prev_cs.reach:
                        cs.localdist_up = (prev_cs.dist - cs.dist)
                    else:
                        cs.localdist_up = cs.reach.length - cs.dist + prev_cs.dist
                    cs.listtosolve.append(prev_cs)
                cs.listtosolve.append(cs)
                cs.position_in_list = 1
                prev_cs = cs
            done_reaches.append(reach)

    # Add the downstream point to listtosolve
    # Also compute the slope for the most upstream points, where the manning's equation is used, and attribute the
    # manning value to each point
    for reach in rivernet.browse_reaches_down_to_up():
        if reach.is_downstream_end():
            prev_cs = None
        else:
            prev_cs = reach.get_downstream_reach().get_last_point(points_coll)
        lastpoint = reach.get_last_point(points_coll)
        for cs in reach.browse_points(points_coll):
            cs.n = manning
            if prev_cs is not None:
                if cs.reach == prev_cs.reach:
                    cs.localdist_down = (cs.dist - prev_cs.dist)
                else:
                    cs.localdist_down = prev_cs.reach.length - prev_cs.dist + cs.dist
                if reach.is_upstream_end() and cs == lastpoint:
                    cs.s = max(min_slope, (cs.wslidar-prev_cs.wslidar)/cs.localdist_down)
                cs.listtosolve.append(prev_cs)
            prev_cs = cs


    # 1D hydraulic calculations, from upstream to downstream. Process main stream first (based on discharge), and stop
    # at confluences.
    stopper = BrowsingStopper()
    done_reaches = []
    for reach in rivernet.browse_reaches_up_to_down(prioritize_reach_attribute="order", stopper=stopper):
        # Looking for the upstream datapoint
        if reach.is_upstream_end():
            prev_cs = None
        # no else: if it's not an upstream reach the prev_cs is already good
        if reach in done_reaches:
            stopper.break_generator = True
        else:
            for cs in reach.browse_points(points_coll, orientation="UP_TO_DOWN"):
                if prev_cs == None:
                    SolverDirect.manning_solver(cs)
                else:
                    # If there is a change of DEM, use the manning solver, with a slope equal to the upstream energy slope
                    if prev_cs.DEM != cs.DEM:
                        cs.s = prev_cs.s
                        SolverDirect.manning_solver(cs)
                    else:
                        # For any other point, use the regular inverse hydraulic solver
                        __recursive_inverse1Dhydro(cs, prev_cs, min_slope, messages, method, supercritical, max_delta_y)
                prev_cs = cs
            done_reaches.append(reach)

    if supercritical:
        # 1D hydraulic calculations, from downstream to upstream. Process main stream first (based on discharge).
        for reach in rivernet.browse_reaches_down_to_up(prioritize_reach_attribute="order"):
            # Looking for the downstream datapoint
            if reach.is_downstream_end():
                prev_cs = None
            # no else: if it's not a downstream reach the prev_cs is already good

            for cs in reach.browse_points(points_coll, orientation="DOWN_TO_UP"):
                if prev_cs != None and (prev_cs.DEM == cs.DEM) and cs.solver != "manning" and cs.solver != "manning up":
                    SolverDirect.cs_solver(cs, min_slope, method, supercritical, max_delta_y, True)
                prev_cs = cs
            done_reaches.append(reach)


    points_coll.add_SavedVariable("solver", "str", 10)
    points_coll.add_SavedVariable("y", "float")
    points_coll.add_SavedVariable("R", "float")
    points_coll.add_SavedVariable("v", "float")
    points_coll.add_SavedVariable("z", "float")
    points_coll.add_SavedVariable("h", "float")
    points_coll.add_SavedVariable("s", "float")
    points_coll.add_SavedVariable("Fr", "float")

    temp_outtable = gc.CreateScratchName("outtable", data_type="ArcInfoTable", workspace="in_memory")
    points_coll.save_points(temp_outtable)
    arcpy.MakeRouteEventLayer_lr(route, route_RID_field, temp_outtable, points_RIDfield + " POINT " + points_distfield, "pts_lyr")
    arcpy.CopyFeatures_management("pts_lyr", output_pts)



def execute_PostSmoothing(route, route_RID_field, route_order_field, routelinks, points, points_IDfield,
                        points_RIDfield, points_distfield, points_Qfield, points_Wfield, points_z_field, points_sfield,
                        points_DEMfield, manning, output_pts, messages, smooth_max_level=20, smoothing_sensitivity=0.001):

    rivernet = RiverNetwork()
    rivernet.dict_attr_fields['id'] = route_RID_field
    rivernet.dict_attr_fields['order'] = route_order_field
    rivernet.load_data(route, routelinks)

    points_coll = Points_collection(rivernet, "data")
    points_coll.dict_attr_fields['id'] = points_IDfield
    points_coll.dict_attr_fields['reach_id'] = points_RIDfield
    points_coll.dict_attr_fields['dist'] = points_distfield
    points_coll.dict_attr_fields['Q'] = points_Qfield
    points_coll.dict_attr_fields['width'] = points_Wfield
    points_coll.dict_attr_fields['z'] = points_z_field
    points_coll.dict_attr_fields['s_valid'] = points_sfield
    points_coll.dict_attr_fields['DEM'] = points_DEMfield
    points_coll.load_table(points)

    simple1Dhydro(rivernet, points_coll, manning, messages)
    messages.AddMessage("Water surface validation done")

    # Collect downstream values
    for reach in rivernet.browse_reaches_down_to_up():
        # Looking for the upstream datapoint
        if reach.is_downstream_end():
            prev_cs = None
        elif reach.get_downstream_reach() != prev_cs.reach:
            prev_cs = reach.get_downstream_reach().get_last_point(points_coll)
        for cs in reach.browse_points(points_coll):
            cs.list_down_z = []
            if prev_cs is not None:
                if len(prev_cs.list_down_z) > 0:
                    cs.list_down_z = prev_cs.list_down_z.copy()
                cs.list_down_z.append(prev_cs.z)
            if len(cs.list_down_z) > smooth_max_level:
                cs.list_down_z.pop(0)
            prev_cs = cs

    # Collect upstream values
    stopper = BrowsingStopper()
    done_reaches = []
    for reach in rivernet.browse_reaches_up_to_down(prioritize_reach_attribute="order", stopper=stopper):
        # Looking for the upstream datapoint
        if reach.is_upstream_end():
            prev_cs = None
        # no else: if it's not an upstream reach the prev_cs is already good
        if reach in done_reaches:
            stopper.break_generator = True
        else:
            for cs in reach.browse_points(points_coll, orientation="UP_TO_DOWN"):
                cs.list_up_z = []
                if prev_cs is not None:
                    if len(prev_cs.list_up_z) > 0:
                        cs.list_up_z = prev_cs.list_up_z.copy()
                    cs.list_up_z.append(prev_cs.z)
                if len(cs.list_up_z) > smooth_max_level:
                    cs.list_up_z.pop(0)

                prev_cs = cs

            done_reaches.append(reach)

    messages.AddMessage("Smoothing")
    # Smoothing
    for reach in rivernet.browse_reaches_down_to_up():
        print(reach.id)
        if reach.is_downstream_end():
            prev_cs = None
        elif reach.get_downstream_reach() != prev_cs.reach:
            prev_cs = reach.get_downstream_reach().get_last_point(points_coll)
        for cs in reach.browse_points(points_coll):

            cs.smoothedz = {}
            cs.smoothedz[0] = cs.z
            level = 1

            while level<=smooth_max_level:
                # Compute the average of bed elevation with one neighbour upstream and downstream (level = 1),
                # 2 neighbours upstream and downstream (level = 2), etc.
                if len(cs.list_down_z)>= level and len(cs.list_up_z)>= level:
                    cs.smoothedz[level] = (cs.list_down_z[-level] + cs.smoothedz[level-1]*(2*level-1) + cs.list_up_z[-level])/(2*level+1)
                level += 1

            cs.n = manning
            cs.smooth_level = 0
            cs.ws_orig_valid = cs.ws_valid
            cs.z_orig = cs.z

            if prev_cs is not None:
                if prev_cs.DEM != cs.DEM:
                    cs.s_valid = prev_cs.s_valid
                    Solver1Dnormal.manning_solver(cs)
                    cs.solver_valid = "manning"
                    cs.type_valid = 0
                else:

                    # Hydraulic is re-computed to have water level from the actual bed elevation
                    Solver1Dnormal.cs_solver(cs, prev_cs)
                    cs.solver_valid = "regular"
                    cs.type_valid = 1

                    cs.ws_test_valid = cs.ws_valid
                    cs.z_orig = cs.z
                    cs.smooth_level = 0

                    valid_smooth = True
                    while cs.smooth_level<=smooth_max_level and valid_smooth:
                        if cs.smooth_level+1 in cs.smoothedz.keys() and prev_cs.smooth_level>=cs.smooth_level:
                            cs.z = cs.smoothedz[cs.smooth_level+1]
                            Solver1Dnormal.cs_solver(cs, prev_cs)
                            if abs(cs.ws_valid - cs.ws_test_valid) < (smoothing_sensitivity/cs.Fr_valid):
                                cs.smooth_level += 1
                            else:
                                cs.z = cs.smoothedz[cs.smooth_level]
                                Solver1Dnormal.cs_solver(cs, prev_cs) #Computation is redone to have the good results
                                valid_smooth = False
                        else:
                            valid_smooth = False
            cs.post_ws = cs.ws_valid
            cs.post_z = cs.z
            prev_cs = cs

    points_coll.add_SavedVariable("post_ws", "float")
    points_coll.add_SavedVariable("post_z", "float")
    #points_coll.add_SavedVariable("z", "float")
    points_coll.add_SavedVariable("smooth_level", "int")

    temp_outtable = gc.CreateScratchName("outtable", data_type="ArcInfoTable", workspace="in_memory")
    points_coll.save_points(temp_outtable)
    arcpy.MakeRouteEventLayer_lr(route, route_RID_field, temp_outtable, points_RIDfield + " POINT " + points_distfield, "pts_lyr")
    arcpy.CopyFeatures_management("pts_lyr", output_pts)

    return

def __recursive_inverse1Dhydro(cs, prev_cs, min_slope, messages, method, supercritical, max_delta_y, working_supercritical=False, ):

    flag = SolverDirect.cs_solver(cs, min_slope, method, supercritical, max_delta_y, working_supercritical)
    if not flag.success:
        # The solver issued a warning
        # It's usually because no solution was found
        # The last attempt is most probably the closest value found, so we keep it, but flag the result and add a warning
        cs.solver = "error"
        messages.addWarningMessage("Bed estimation failed at reach ID {} dist {:.2f}m: {}".format(cs.reach.id, cs.dist, flag.message))

    # Adding a cross-section if the Froude number varies too much, if method = "OVERSAMPLING"

    localdist = cs.localdist_up
    if method=="OVERSAMPLING" and abs(cs.Fr - prev_cs.Fr) / prev_cs.Fr > 0.5 and localdist > 0.1: # Minimum 10cm between cs
        if not working_supercritical:
            if cs.reach == prev_cs.reach:
                newcs = cs.reach.add_point((cs.dist + prev_cs.dist) / 2., cs.points_collection)
            else:
                # case where the interpolation takes place between two reaches
                if localdist / 2. < prev_cs.dist:
                    # point is in the upstream reach (prev_cs reach)
                    newcs = prev_cs.reach.add_point(localdist / 2., cs.points_collection)

                else:
                    newcs = cs.reach.add_point(cs.dist + localdist / 2., cs.points_collection)
        else:
            if cs.reach == prev_cs.reach:
                newcs = cs.reach.add_point((cs.dist + prev_cs.dist) / 2., cs.points_collection)
            else:
                # case where the interpolation takes place between two reaches
                if prev_cs.dist + localdist / 2. < prev_cs.reach.length:
                    # point is in the downstream reach (prev_cs reach)
                    newcs = prev_cs.reach.add_point(prev_cs.dist + localdist / 2., cs.points_collection)

                else:
                    newcs = cs.reach.add_point(localdist / 2. - (prev_cs.reach.length - prev_cs.dist),
                                               cs.points_collection)

        # Linear interpolation of width, discharge and water surface.
        # Although more accurate spatialization could be done, this is deemed accurate enough
        a = (cs.width - prev_cs.width) / (0-localdist)
        newcs.width = a * localdist/2. + cs.width
        a = (cs.Q - prev_cs.Q) / (0-localdist)
        newcs.Q = a * localdist/2. + cs.Q
        a = (cs.wslidar - prev_cs.wslidar) / (0-localdist)
        newcs.wslidar = a* localdist/2. + cs.wslidar
        newcs.n = cs.n
        #newcs.s_min = 0
        newcs.DEM = prev_cs.DEM
        newcs.solver = "regular"

        newcs.listtosolve = [prev_cs, newcs]
        newcs.position_in_list = 1
        cs.listtosolve = [newcs, cs]
        cs.position_in_list = 1

        if not working_supercritical:
            cs.localdist_up = localdist / 2.
            newcs.localdist_up = localdist / 2.
            newcs.localdist_down = localdist / 2.
            prev_cs.localdist_down = localdist / 2.
            cs.listtosolve[0] = newcs
            newcs.listtosolve = [prev_cs, newcs, cs]
            prev_cs.listtosolve[-1] = newcs
            newcs.position_in_list = 1
        else:
            cs.localdist_down = localdist / 2.
            newcs.localdist_down = localdist / 2.
            newcs.localdist_up = localdist / 2.
            prev_cs.localdist_up = localdist / 2.
            cs.listtosolve[-1] = newcs
            newcs.listtosolve = [cs, newcs, prev_cs]
            prev_cs.listtosolve[0] = newcs
            newcs.position_in_list = 1

        __recursive_inverse1Dhydro(newcs, prev_cs, min_slope, messages, method, supercritical, working_supercritical)
        __recursive_inverse1Dhydro(cs, newcs, min_slope, messages, method, supercritical, working_supercritical)

    return

