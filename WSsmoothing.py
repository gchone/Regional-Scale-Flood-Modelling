# coding: latin-1



import os
import arcpy

from tree.RiverNetwork import *
from QuantileRegression import QuantileCarving




def execute_WSsmoothing(network_shp, links_table, RID_field, order_field, datapoints, id_field_pts, RID_field_pts, Distance_field_pts, dem_z_field, dem_forws_field, DEM_ID_field, output_points, messages, smooth_perc = 0.9):

    # The smoothing process :
    # - Removes bumps in the water surface profile following the quantile carving process of
    #   Schwanghart and Scherler (2017). See QuantileRegression.py for details.
    # - Smooths the river profile according to the estimated uncertainty. Uncertainty is assessed by the difference
    #   between the maximum elevation downstream and the minimum elevation upstream any point in the profile.
    # An additionnal smoothing was tested but not put into production. This smoothing process divides the profile into
    #   reaches where a linear regression in done.

    network = RiverNetwork()
    network.dict_attr_fields['id'] = RID_field
    network.dict_attr_fields['order'] = order_field
    network.load_data(network_shp, links_table)

    collection = Points_collection(network, "data")
    collection.dict_attr_fields['id'] = id_field_pts
    collection.dict_attr_fields['reach_id'] = RID_field_pts
    collection.dict_attr_fields['dist'] = Distance_field_pts
    collection.dict_attr_fields['zerr'] = dem_z_field
    collection.dict_attr_fields['z_forws'] = dem_forws_field
    collection.dict_attr_fields['DEM_ID'] = DEM_ID_field
    collection.load_table(datapoints)

    # First, the network is browsed from down to up to have the highest limit of the error (cs.z_fill)
    #  and then from up to down to have the lowest limit of the error (cs.z_breach)

    # When doing this first down to up, we can also compute the fill version by DEM of the water surface, which is the
    #  right data to use as the water surface for hydraulic modeling (cs.ztosmooth)
    # June 2022 modification : Instead of a fill, quantile carving

    for reach in network.browse_reaches_down_to_up():
        if reach.is_downstream_end():
            prev_cs = None
        elif reach.get_downstream_reach() != prev_cs.reach:
            prev_cs = reach.get_downstream_reach().get_last_point(collection)
        for cs in reach.browse_points(collection):

            if prev_cs != None and cs.DEM_ID == prev_cs.DEM_ID:
                cs.z_fill = max(prev_cs.z_fill, cs.zerr)
                #cs.ztosmooth = max(prev_cs.ztosmooth, cs.z_forws)
            else:
                cs.z_fill = cs.zerr
                #cs.ztosmooth = cs.z_forws
            # z_breach à None permet le bon breach pour les parties parcourues plusieurs fois
            cs.z_breach = None
            prev_cs = cs

    # up to down
    for reach in network.browse_reaches_up_to_down():
        if reach.is_upstream_end():
            prev_cs = None
        for cs in reach.browse_points(collection, orientation="UP_TO_DOWN"):
            if prev_cs != None and cs.DEM_ID == prev_cs.DEM_ID:
                if cs.z_breach != None:
                    cs.z_breach = min(prev_cs.z_breach, cs.zerr, cs.z_breach)
                else:
                    cs.z_breach = min(prev_cs.z_breach, cs.zerr)
            else:
                cs.z_breach = cs.zerr
            prev_cs = cs

    # Quantile carving is done for datapoints along the same river (not stopped at confluences) from the same DEM
    list_cs = []
    prev_DEM_ID = None
    restartdown = False
    for reach in network.browse_reaches_down_to_up(prioritize_reach_attribute="order"):
        if reach.is_downstream_end():
            prev_cs = None
            prevcs_list = None # downstream point of the current list
        elif reach.get_downstream_reach() != prev_cs.reach:
            prev_cs = reach.get_downstream_reach().get_last_point(collection)
            if restartdown: # last treated reach was an upstream end
                prevcs_list = prev_cs
        isendreach = reach.is_upstream_end()
        endnode = reach.get_last_point(collection)
        for cs in reach.browse_points(collection):
            # Stop when there is a DEM change or when we reach the last cs upstream
            if prev_DEM_ID is not None and prev_DEM_ID != cs.DEM_ID:
                QuantileCarving(list_cs, prevcs_list, messages)
                list_cs = []
                prevcs_list = None
                restartdown = False
            prev_DEM_ID = cs.DEM_ID
            list_cs.append(cs)

            if isendreach and cs==endnode:
                QuantileCarving(list_cs, prevcs_list, messages)
                list_cs = []
                prev_DEM_ID = None
                restartdown = True
            prev_cs = cs

    # indépendance par rapport à la résolution:
    #   La méthode de base pondère le résultat final en fonction de la valeur au point et de la valeur précédente
    #   (majorée/minorée par le fill ou le breach). L'indépendance par rapport à la résolution est faire en corrigeant
    #   le poid par la puissance du ratio des distances. Le poid de base était pensé pour une résolution de 10m.
    #   Ex : Résolution de 2m. On parcourt 5 pixels pour l'équivalent de un pixel à 10m. Si le poid est de 0.9
    #   pour 10m), z = 0.9z, dans le cas d'une chute à 0 (profil en forme de marche), il faut à 2m de résolution
    #   z*poid^5 pour avoir l'équivalent, donc poid^5=0.9, donc poid=0.9^(1/5)
    # down to up

    for reach in network.browse_reaches_down_to_up():

        if reach.is_downstream_end():
            prev_cs = None
        elif reach.get_downstream_reach() != prev_cs.reach:
            prev_cs = reach.get_downstream_reach().get_last_point(collection)
        for cs in reach.browse_points(collection):
            if prev_cs != None and cs.DEM_ID == prev_cs.DEM_ID:
                if prev_cs.reach == cs.reach:
                    localdist = (cs.dist - prev_cs.dist)
                else:
                    localdist = prev_cs.reach.length - prev_cs.dist + cs.dist

                cs.zsmooth2 = max(((1 - smooth_perc ** (localdist / 10.)) * cs.ztosmooth + smooth_perc ** (localdist / 10.) * prev_cs.zsmooth2), cs.z_breach)

            else:
                cs.zsmooth2 = cs.ztosmooth
            prev_cs = cs
    # up to down
    for reach in network.browse_reaches_up_to_down():
        if reach.is_upstream_end():
            prev_cs = None
        for cs in reach.browse_points(collection, orientation="UP_TO_DOWN"):
            if prev_cs != None and cs.DEM_ID == prev_cs.DEM_ID:
                if prev_cs.reach == cs.reach:
                    localdist = (prev_cs.dist - cs.dist)
                else:
                    localdist = cs.reach.length - cs.dist + prev_cs.dist
                if hasattr(cs, "zsmooth1"):
                    cs.zsmooth1 = min((
                        (1 - smooth_perc ** (localdist / 10.)) * cs.ztosmooth + smooth_perc ** (localdist / 10.) *
                            prev_cs.zsmooth1), cs.z_fill, cs.zsmooth1)
                else:
                    cs.zsmooth1 = min(((1 - smooth_perc ** (localdist / 10.)) * cs.ztosmooth + smooth_perc ** (localdist / 10.) * prev_cs.zsmooth1), cs.z_fill)
            else:
                cs.zsmooth1 = cs.ztosmooth
            cs.zsmooth = (cs.zsmooth1 + cs.zsmooth2)/2.
            prev_cs = cs


    # ADDITIONNAL SMOOTHING
    # Take one reach at a time, and consider the first and the last point as fixed.
    # Does a linear interpolation between these two points, at each point
    # Compute the difference between the linear interpolated elevation, and the measure elevation at each point
    # If the max difference is higher than the tolerance, the reach is split in 2 at that point.
    # Done recursively

    # First, the base segments are datapoints along the same river (not stopped at confluences) from the same DEM
    # list_cs = []
    # prev_DEM_ID = None
    # for reach in network.browse_reaches_down_to_up(prioritize_reach_attribute="order"):
    #     isendreach = reach.is_upstream_end()
    #     endnode = reach.get_last_point(collection)
    #     for cs in reach.browse_points(collection):
    #         # Stop when there is a DEM change or when we reach the last cs upstream
    #         if prev_DEM_ID is not None and prev_DEM_ID != cs.DEM_ID:
    #             __recursive_additionalsmoothing(list_cs, tolerance)
    #             list_cs = []
    #         prev_DEM_ID = cs.DEM_ID
    #         list_cs.append(cs)
    #
    #         if isendreach and cs==endnode:
    #             __recursive_additionalsmoothing(list_cs, tolerance)
    #             list_cs = []
    #             prev_DEM_ID = None

    collection.add_SavedVariable("zsmooth", "float")
    collection.add_SavedVariable("ztosmooth", "float")
    #collection.add_SavedVariable("finalz", "float")
    collection.save_points(output_points)

    return

def __recursive_additionalsmoothing(list_cs, tolerance):
    a = (list_cs[-1].zsmooth - list_cs[0].zsmooth) / (list_cs[-1].dist - list_cs[0].dist)
    b = list_cs[0].zsmooth - a * list_cs[0].dist
    max_dif_index = -999
    max_dif = -999
    list_cs[0].finalz = list_cs[0].zsmooth
    list_cs[-1].finalz = list_cs[-1].zsmooth
    if len(list_cs)>2:
        for i in range(1, len(list_cs)-1):
            interpolatedZ = a * list_cs[i].dist + b
            dif = abs(interpolatedZ - list_cs[i].zsmooth)
            if dif > max_dif:
                max_dif = dif
                max_dif_index = i
        if max_dif > tolerance:
            # Recursive call
            __recursive_additionalsmoothing(list_cs[:max_dif_index+1], tolerance)
            __recursive_additionalsmoothing(list_cs[max_dif_index:], tolerance)
        else:
            # Interpolated values are used
            for cs in list_cs:
                cs.finalz = a * cs.dist + b

