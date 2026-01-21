# -*- coding: utf-8 -*-

#####################################################
# Guénolé Choné
# Concordia University
# Geography, Planning and Environment Department
# guenole.chone@concordia.ca
#####################################################


import os
import arcpy

from tree.TreeTools import *
from tree.RiverNetwork import *

def execute_DownstreamSlope(route, route_RID_field, routelinks, points, points_IDfield, points_RIDfield, points_distfield,
     points_z_field, points_DEMfield, output_pts, messages):

    rivernet = RiverNetwork()
    rivernet.dict_attr_fields['id'] = route_RID_field
    rivernet.load_data(route, routelinks)

    points_coll = Points_collection(rivernet, "data")
    points_coll.dict_attr_fields['id'] = points_IDfield
    points_coll.dict_attr_fields['reach_id'] = points_RIDfield
    points_coll.dict_attr_fields['dist'] = points_distfield
    points_coll.dict_attr_fields['z'] = points_z_field
    points_coll.dict_attr_fields['DEM'] = points_DEMfield

    points_coll.load_table(points)

    points_coll.add_SavedVariable("ws_slope", "float")

    for reach in rivernet.browse_reaches_down_to_up():
        # Looking for the upstream datapoint
        if reach.is_downstream_end():
            prev_cs = None
        elif reach.get_downstream_reach() != prev_cs.reach:
            prev_cs = reach.get_downstream_reach().get_last_point(points_coll)
        for cs in reach.browse_points(points_coll):

            if prev_cs == None:
                cs.ws_slope = -999

            else:

                if prev_cs.DEM != cs.DEM:
                    cs.ws_slope = -999
                else:
                    if prev_cs.reach == cs.reach:
                        localdist = (cs.dist - prev_cs.dist)
                    else:
                        localdist = prev_cs.reach.length - prev_cs.dist + cs.dist
                    cs.ws_slope = (cs.z-prev_cs.z)/localdist

            prev_cs = cs

    points_coll.save_points(output_pts)

    return

