# -*- coding: utf-8 -*-


# ArcGIS tools for tree manipulation
import arcpy
import numpy as np

from tree.RiverNetwork import *

def execute_InterpolatePoints(points_table, id_field_pts, RID_field_pts, Distance_field_pts, data_fields, targetpoints, id_field_target, RID_field_target, Distance_field_target, network_shp, links_table, network_RID_field, order_field, ouput_table, extrapolation_value=None):
    # extrapolation_value = None : first upstream (or last downstream value) in the data copied for target points more downstream (or upstream)
    # extrapolation_value = "CONFLUENCE" : same as extrapolation_value = None, with in addition no interpolation at confluences (first upstream value used) (used for width)
    # extrapolation_value numeric : value used downstream (or upstream) of data values

    network = RiverNetwork()
    network.dict_attr_fields['id'] = network_RID_field
    network.dict_attr_fields['order'] = order_field
    network.load_data(network_shp, links_table)

    datacollection = Points_collection(network, "data")
    datacollection.dict_attr_fields['id'] = id_field_pts
    datacollection.dict_attr_fields['reach_id'] = RID_field_pts
    datacollection.dict_attr_fields['dist'] = Distance_field_pts
    for field in data_fields:
        datacollection.dict_attr_fields[field] = field
    datacollection.load_table(points_table)

    targetcollection = Points_collection(network, "target")
    targetcollection.dict_attr_fields['id'] = id_field_target
    targetcollection.dict_attr_fields['reach_id'] = RID_field_target
    targetcollection.dict_attr_fields['dist'] = Distance_field_target
    targetcollection.load_table(targetpoints)

    newarray = InterpolatePoints_with_objects(network, datacollection, data_fields, targetcollection, extrapolation_value)

    arcpy.da.NumPyArrayToTable(newarray, ouput_table)


def InterpolatePoints_with_objects(network, datacollection, data_fields, targetcollection, extrapolation_value, subdatasample = None):

    # Gather metadata for the new array
    newdtype = []

    dict_attr_output_fields = targetcollection.dict_attr_fields.copy()

    for attr, field in dict_attr_output_fields.items():
        newdtype.append(
            (str(field), targetcollection._numpyarray.dtype.fields[targetcollection.dict_attr_fields[attr]][0]))
    for field in data_fields:
        newdtype.append(
            (str(field), datacollection._numpyarray.dtype.fields[datacollection.dict_attr_fields[attr]][0]))
    newarray = None

    for reach in network.browse_reaches_down_to_up():
        if subdatasample is not None:
            datatointerp = subdatasample
        else:
            datatointerp = datacollection._numpyarray
        targetdata = np.sort(
            targetcollection._numpyarray[
                targetcollection._numpyarray[targetcollection.dict_attr_fields['reach_id']] == reach.id],
            order=targetcollection.dict_attr_fields['dist'])
        sorteddata = np.sort(
            datatointerp[
                datatointerp[datacollection.dict_attr_fields['reach_id']] == reach.id],
            order=datacollection.dict_attr_fields['dist'])

        # browsing down until we find a reach with at least one point
        down_point = None
        down_reach = reach
        downend = reach.is_downstream_end()
        same_river_down_reach_order = reach.order # this variable is used to identify if we stay on the same river (as opposed as we meet a larger one)
        while down_point is None and not downend:
            down_reach = down_reach.get_downstream_reach()
            same_river_down_reach_order -= 1
            if extrapolation_value != "CONFLUENCE" or down_reach.order == same_river_down_reach_order:
                downpoints =np.sort(
                    datatointerp[
                        datatointerp[datacollection.dict_attr_fields['reach_id']] == down_reach.id],
                    order=datacollection.dict_attr_fields['dist'])
                if len(downpoints) > 0:
                    down_point = downpoints[-1]
                    # update the distance
                    down_point[datacollection.dict_attr_fields['dist']] = down_point[datacollection.dict_attr_fields[
                        'dist']] - down_reach.length
                    # add the most upstream point in the downstream reach in the data
                    sorteddata = np.concatenate(([down_point], sorteddata))
                downend = down_reach.is_downstream_end()
            else:
                downend = True

        # browsing up until we find a reach with at least one point
        up_point = None
        up_reach = reach
        upend = reach.is_upstream_end()

        while up_point is None and not upend:
            min_order = None
            for tmp_up_reach in up_reach.get_uptream_reaches():
                # the upstream reach to use is the one with the smallest order
                if min_order is None or tmp_up_reach.order < min_order:
                    min_order = tmp_up_reach.order
                    up_reach = tmp_up_reach

            uppoints = np.sort(
                datatointerp[
                    datatointerp[datacollection.dict_attr_fields['reach_id']] == up_reach.id],
                order=datacollection.dict_attr_fields['dist'])

            if len(uppoints) > 0:
                up_point = uppoints[0]
                # update the distance
                up_point[datacollection.dict_attr_fields['dist']] = up_point[datacollection.dict_attr_fields['dist']] + reach.length
                # add the most downstream point in the upstream reach in the data
                sorteddata = np.concatenate((sorteddata, [up_point]))
            upend = up_reach.is_upstream_end()

        newres = np.empty(targetdata.shape[0], dtype=newdtype)

        if extrapolation_value is None or extrapolation_value == "CONFLUENCE":
            interp_left_right_param = None
        else:
            interp_left_right_param = extrapolation_value

        for field, value in dict_attr_output_fields.items():
            newres[value] = targetdata[targetcollection.dict_attr_fields[field]]

        for field in data_fields:
            if len(sorteddata) > 0:
                interp = np.interp(targetdata[targetcollection.dict_attr_fields['dist']], sorteddata[datacollection.dict_attr_fields['dist']], sorteddata[field], left=interp_left_right_param, right=interp_left_right_param)
                newres[field] = interp
            else:
                newres[field] = float(extrapolation_value) # case of a reach without any data point

        # Create a new array or update it
        if newarray is None:
            newarray = np.copy(newres)
        else:
            newarray = np.concatenate((newarray, newres))

    return newarray