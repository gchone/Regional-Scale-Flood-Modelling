# -*- coding: utf-8 -*-

#####################################################
# Guénolé Choné
# Concordia University
# Geography, Planning and Environment Department
# guenole.chone@concordia.ca
#####################################################


import os
import arcpy
import pickle
from RasterIO import *
from tree.RiverNetwork import *
from Solver1Dnormal import *


def execute_BedAssessment(route, route_RID_field, route_order_field, routelinks, points, points_IDfield, points_RIDfield, points_distfield, points_Qfield, points_Wfield, points_WSfield, points_DEMfield, manning, output_pts, messages):

    downstream_s = 0.0001

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

    points_coll.add_SavedVariable("solver", "str", 10)
    points_coll.add_SavedVariable("y", "float")
    points_coll.add_SavedVariable("R", "float")
    points_coll.add_SavedVariable("v", "float")
    points_coll.add_SavedVariable("z", "float")
    points_coll.add_SavedVariable("h", "float")
    points_coll.add_SavedVariable("s", "float")
    points_coll.add_SavedVariable("Fr", "float")

    enditeration = False
    iteration = 0
    while not enditeration:
        iteration += 1

        # 1D hydraulic calculations
        for reach in rivernet.browse_reaches_down_to_up():
            # Looking for the downstream datapoint
            if reach.is_downstream_end():
                prev_cs = None
            else:
                prev_cs = reach.get_downstream_reach().get_last_point(points_coll)

            for cs in reach.browse_points(points_coll):
                cs.n = manning
                if iteration == 1:
                    if prev_cs != None and prev_cs.DEM == cs.DEM:
                        # Fill
                        cs.wslidar = max(prev_cs.wslidar, cs.wslidar)
                    cs.z = cs.wslidar
                    cs.ws = cs.wslidar


                if prev_cs == None:

                    # downstream cs calculation
                    cs.s = downstream_s
                    manning_solver(cs)
                    cs.v = cs.Q / (cs.width * cs.y)
                    cs.h = cs.z + cs.y + cs.v ** 2 / (2 * g)
                    cs.Fr = cs.v / (g * cs.y) ** 0.5
                    cs.solver = "manning"
                    cs.type = 0

                else:
                    if prev_cs.DEM != cs.DEM:
                        cs.s = prev_cs.s
                        manning_solver(cs)
                        cs.solver = "manning"
                        cs.type = 0
                    else:
                        cs_solver(cs, prev_cs)
                        cs.solver = "regular"
                        cs.type = 1

                cs.prev_ws = cs.ws
                cs.ws = cs.z + cs.y
                cs.dif = cs.ws - cs.wslidar


                prev_cs = cs




        corrections = []
        # down to up
        for reach in rivernet.browse_reaches_down_to_up():
            # Looking for the downstream datapoint
            if reach.is_downstream_end():
                prev_cs = None
            else:
                prev_cs = reach.get_downstream_reach().get_last_point(points_coll)

            for cs in reach.browse_points(points_coll):
                if prev_cs != None:
                    if prev_cs.z_fill > cs.z:
                        if prev_cs.z == prev_cs.z_fill:
                            # first backwater cell
                            correction = []
                            corrections.append(correction)
                            cs.idcorrection = len(corrections) - 1
                        else:
                            correction = corrections[prev_cs.idcorrection]
                            cs.idcorrection = prev_cs.idcorrection
                        cs.z_fill = prev_cs.z_fill
                        correction.append(cs)
                    else:
                        cs.z_fill = cs.z
                        correction = []
                        correction.append(cs)
                        corrections.append(correction)
                        cs.idcorrection = len(corrections) - 1
                else:
                    cs.z_fill = cs.z
                    correction = []
                    correction.append(cs)
                    corrections.append(correction)
                    cs.idcorrection = len(corrections) - 1

                prev_cs = cs

        enditeration = True
        for correction in corrections:
            sumdif = 0
            sumdifws = 0
            for cscorrect in correction:
                sumdif += cscorrect.dif
                sumdifws += cscorrect.ws - cscorrect.prev_ws
            correcteddif = sumdif / len(correction)
            difws = abs(sumdifws) / len(correction)
            if difws > 0.01:
                for cscorrect in correction:
                    cscorrect.z = cscorrect.z - correcteddif
                enditeration = False

    points_coll.save_points(output_pts)

    return



