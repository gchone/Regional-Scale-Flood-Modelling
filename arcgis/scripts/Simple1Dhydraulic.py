# -*- coding: utf-8 -*-

#####################################################
# Guénolé Choné
# Concordia University
# Geography, Planning and Environment Department
# guenole.chone@concordia.ca
#####################################################


import os
import arcpy

import Solver1Dnormal
from tree.TreeTools import *
from tree.RiverNetwork import *

def execute_Simple1Dhydraulic(route, route_RID_field, route_order_field, routelinks, points, points_IDfield, points_RIDfield, points_distfield,
     points_Qfield, points_Wfield, points_z_field, points_DEMfield, manning, down_slope, output_pts, messages):

    rivernet = RiverNetwork()
    rivernet.dict_attr_fields['id'] = route_RID_field
    rivernet.dict_attr_fields['order'] = route_order_field
    rivernet.load_data(route, routelinks)

    points_coll = Points_collection(rivernet, "data")
    points_coll.dict_attr_fields['id'] = points_IDfield
    points_coll.dict_attr_fields['reach_id'] = points_RIDfield
    points_coll.dict_attr_fields['dist'] = points_distfield
    points_coll.dict_attr_fields['z'] = points_z_field
    points_coll.dict_attr_fields['Q'] = points_Qfield
    points_coll.dict_attr_fields['width'] = points_Wfield
    points_coll.dict_attr_fields['DEM'] = points_DEMfield

    points_coll.load_table(points)

    # Initiate slope at the downstream points
    reaches = rivernet.get_downstream_ends()
    for reach in reaches:
        cs = reach.get_first_point(points_coll)
        cs.s_valid = down_slope

    simple1Dhydro(rivernet, points_coll, manning, messages)

    points_coll.add_SavedVariable("solver_valid", "str", 10)
    points_coll.add_SavedVariable("y_valid", "float")
    points_coll.add_SavedVariable("R_valid", "float")
    points_coll.add_SavedVariable("v_valid", "float")
    points_coll.add_SavedVariable("ws_valid", "float")
    points_coll.add_SavedVariable("h_valid", "float")
    points_coll.add_SavedVariable("s_valid", "float")
    points_coll.add_SavedVariable("Fr_valid", "float")

    points_coll.save_points(output_pts)

    return

def simple1Dhydro(rivernet, points_coll, manning, messages):

    for reach in rivernet.browse_reaches_down_to_up():
        # Looking for the upstream datapoint
        if reach.is_downstream_end():
            prev_cs = None
        elif reach.get_downstream_reach() != prev_cs.reach:
            prev_cs = reach.get_downstream_reach().get_last_point(points_coll)
        for cs in reach.browse_points(points_coll):

            cs.n = manning

            if prev_cs == None:

                # downstream cs calculation
                Solver1Dnormal.manning_solver(cs)
                cs.solver_valid = "manning"
                cs.type_valid = 0

            else:
                if prev_cs.DEM != cs.DEM:
                    cs.s_valid = prev_cs.s_valid
                    Solver1Dnormal.manning_solver(cs)

                    cs.solver_valid = "manning"
                    cs.type_valid = 0
                else:

                    Solver1Dnormal.cs_solver(cs, prev_cs)
                    cs.solver_valid = "regular"
                    cs.type_valid = 1

            prev_cs = cs



    return

