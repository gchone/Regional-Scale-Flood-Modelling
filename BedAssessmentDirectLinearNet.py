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


def execute_BedAssessment(route, route_RID_field, route_order_field, routelinks, points, points_IDfield,
                          points_RIDfield, points_distfield, points_Qfield, points_Wfield, points_WSfield,
                          points_DEMfield, manning, min_slope, output_pts, messages):

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

    ### TENTATIVE DE LIAISON DES CS ###
    ### Remplace le calcul de pente au départ
    ### La pente devrait être calculée dynamiquement
    ### CHANGER LES PARTIES IDENTIFIANT prev_cs et la distance AILLEURS !!!!!

    # # Downstream cross-section is linked to upstream cross-section with cs.down_cs. Distance is also added with
    # # cs.down_cs_dist
    # stopper = BrowsingStopper()
    # done_reaches = []
    # for reach in rivernet.browse_reaches_up_to_down(prioritize_reach_attribute="order", stopper=stopper):
    #     if prev_cs is not None:
    #         prev_cs.down_cs_dist = prev_cs.down_cs_dist + reach.length
    #     if reach in done_reaches:
    #         stopper.break_generator = True
    #         cs = reach.get_last_point(points_coll)
    #         if cs is not None:
    #             prev_cs.down_cs = cs
    #             prev_cs.down_cs_dist = prev_cs.down_cs_dist - prev_cs.dist
    #         # If the reach is already done, we don't need to process it again
    #         done_reaches.append(reach)
    #     else:
    #         for cs in reach.browse_points(points_coll, orientation="UP_TO_DOWN"):
    #             if prev_cs is not None:
    #                 prev_cs.down_cs = cs
    #                 prev_cs.down_cs_dist = prev_cs.down_cs_dist - prev_cs.dist
    #             cs.down_cs_dist = cs.dist
    #             prev_cs = cs
    #
    #         done_reaches.append(reach)

    # Slope is added to all points. It's computed from the downstream point. It's in fact latter used only for the most
    # upstream points, where the manning's equation is used.

    for reach in rivernet.browse_reaches_down_to_up():
        if reach.is_downstream_end():
            prev_cs = None
        else:
            prev_cs = reach.get_downstream_reach().last_point
        for cs in reach.browse_points(points_coll):
            if prev_cs is not None:
                if cs.reach == prev_cs.reach:
                    localdist = (cs.dist - prev_cs.dist)
                else:
                    localdist = prev_cs.reach.length - prev_cs.dist + cs.dist
                cs.s = max(min_slope, (cs.wslidar-prev_cs.wslidar)/localdist)
            prev_cs = cs
        reach.last_point = cs

    # # hardcoded parameter: Minimum difference of water surface elevation for backwater area
    # delta_z_min = 0.01
    #
    # # First pass to identify minimum slope for backwater area and upstream boundary condition
    # backwater_pts = []
    # length = 0
    # prev_cs = None
    # for reach in rivernet.browse_reaches_down_to_up():
    #     lastpoint = reach.get_last_point(points_coll)
    #     for cs in reach.browse_points(points_coll):
    #         if prev_cs is not None:
    #             if cs.reach == prev_cs.reach:
    #                 localdist = (cs.dist - prev_cs.dist)
    #             else:
    #                 localdist = prev_cs.reach.length - prev_cs.dist + cs.dist
    #
    #             if cs.wslidar <= prev_cs.wslidar:
    #                 backwater_pts.append(cs)
    #                 length += localdist
    #             else:
    #                 cs.s_min = 0
    #                 for backcs in backwater_pts:
    #                     backcs.s_min = delta_z_min/length
    #                 length = 0
    #                 backwater_pts = []
    #         else:
    #             cs.s_min = 0
    #         if reach.is_upstream_end():
    #             if cs == lastpoint:
    #                 for backcs in backwater_pts:
    #                     backcs.s_min = delta_z_min/length
    #                 length = 0
    #                 backwater_pts = []
    #                 cs.s = max(cs.s_min, (cs.wslidar-prev_cs.wslidar)/localdist) # Compute upstream boundary condition
    #         prev_cs = cs # ERREUR A CORRIGER : CHANGEMENT DE REACH

    # Current behaviour is to process main stream in priority (based on discharge)
    # Process is stopped when meeting an already-processed reach (bathymetry is never computed twice)

    # 1D hydraulic calculations
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
                cs.n = manning

                if prev_cs == None:
                    SolverDirect.manning_solver(cs)
                    cs.solver = "manning up"
                    cs.type = 0

                else:
                    if prev_cs.DEM != cs.DEM:
                        cs.s = prev_cs.s
                        SolverDirect.manning_solver(cs)
                        cs.solver = "manning"
                        cs.type = 0
                    else:
                        cs.solver = "regular"
                        cs.type = 1
                        __recursive_inverse1Dhydro(cs, prev_cs, min_slope)

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
    points_coll.save_points(output_pts)



def execute_PostSmoothing(route, route_RID_field, route_order_field, routelinks, points, points_IDfield,
                        points_RIDfield, points_distfield, points_Qfield, points_Wfield, points_WSfield, points_z_field, points_sfield,
                        points_Frfield, points_DEMfield, manning, output_pts, messages):

    rivernet = RiverNetwork()
    rivernet.dict_attr_fields['id'] = route_RID_field
    rivernet.dict_attr_fields['order'] = route_order_field
    rivernet.load_data(route, routelinks)

    points_coll = Points_collection(rivernet, "data")
    points_coll.dict_attr_fields['id'] = points_IDfield
    points_coll.dict_attr_fields['reach_id'] = points_RIDfield
    points_coll.dict_attr_fields['dist'] = points_distfield
    points_coll.dict_attr_fields['ws_valid'] = points_WSfield
    points_coll.dict_attr_fields['Q'] = points_Qfield
    points_coll.dict_attr_fields['width'] = points_Wfield
    points_coll.dict_attr_fields['z'] = points_z_field
    points_coll.dict_attr_fields['s_valid'] = points_sfield
    points_coll.dict_attr_fields['Fr'] = points_Frfield
    points_coll.dict_attr_fields['DEM'] = points_DEMfield
    points_coll.load_table(points)

    simple1Dhydro(rivernet, points_coll, manning, messages)


    smooth_max_level = 20
    smoothing_sensitivity = 0.001

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

    # Smoothing
    for reach in rivernet.browse_reaches_down_to_up():
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
                            if abs(cs.ws_valid - cs.ws_test_valid) < (smoothing_sensitivity/cs.Fr):
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

    points_coll.save_points(output_pts)

    return

def __recursive_inverse1Dhydro(cs, prev_cs, min_slope):

    flag = SolverDirect.cs_solver(prev_cs, cs, min_slope)
    if not flag.success:
        # The solver issued a warning
        # It's usually because no solution was found
        # The last attempt is the closes value found, so we keep it
        cs.solver = "error"
        cs.type = -999

    if cs.reach == prev_cs.reach:
        localdist = (prev_cs.dist - cs.dist)
    else:
        localdist = cs.reach.length - cs.dist + prev_cs.dist

    # Adding a cross-section if the Froude number varies too much
    if (cs.Fr - prev_cs.Fr) / prev_cs.Fr > 0.5 and localdist > 0.1: # Minimum 10cm between cs

        if cs.reach == prev_cs.reach:
            newcs = cs.reach.add_point((cs.dist + prev_cs.dist) / 2., cs.points_collection)
        else:
            # case where the interpolation takes place between two reaches
            if localdist / 2. < prev_cs.dist:
                # point is in the upstream reach (prev_cs reach)
                newcs = prev_cs.reach.add_point(localdist / 2., cs.points_collection)

            else:
                newcs = cs.reach.add_point(cs.dist + localdist / 2., cs.points_collection)

        newlocaldist = localdist / 2.
        # Linear interpolation of width, discharge and water surface.
        # Although more accurate spatialization could be done, this is deemed accurate enough
        a = (cs.width - prev_cs.width) / (0-localdist)
        newcs.width = a * newlocaldist + cs.width
        a = (cs.Q - prev_cs.Q) / (0-localdist)
        newcs.Q = a * newlocaldist + cs.Q
        a = (cs.wslidar - prev_cs.wslidar) / (0-localdist)
        newcs.wslidar = a* newlocaldist + cs.wslidar
        newcs.n = cs.n
        #newcs.s_min = 0
        newcs.DEM = prev_cs.DEM
        newcs.solver = "regular"
        __recursive_inverse1Dhydro(newcs, prev_cs, min_slope)
        #newcs.solver = "added"
        newcs.type = 3
        __recursive_inverse1Dhydro(cs, newcs, min_slope)

    return

