# coding: latin-1



import os
import arcpy

from tree.RiverNetwork import *
from QuantileRegression import QuantileCarving
from scipy.stats import norm
from scipy.optimize import minimize_scalar
import math
import warnings
from rdp import rdp
import numpy as np
from scipy.interpolate import interp1d



def Gaussian_weighted_moving_average(listcs, prev_cs, sigma, uncertaintysigma, uncertaintyfactor, slopesigma, slopefactor):

    if prev_cs is None:
        minz = -math.inf
    else:
        minz = prev_cs.zws_smoothed

    reachdist = 0
    distances = []
    values = []
    unbreached_values = []
    lastreach = None
    for cs in listcs:
        if lastreach is not None and cs.reach != lastreach:
            reachdist += lastreach.length
        distances.append(cs.dist + reachdist)
        values.append(max(cs.zws_quantilecarving, minz))  # "Fill" with the downstream z value (so z never gets lower)
        unbreached_values.append(cs.z_forws)
        lastreach = cs.reach
    distances = np.array(distances)
    values = np.array(values)
    unbreached_values = np.array(unbreached_values)

    carving = unbreached_values - values
    smoothed_values = np.zeros_like(values)
    uncertainty_vec = np.zeros_like(values)
    restricted = np.zeros_like(values)
    sd2_vec = np.zeros_like(values)
    local_sigma_vec = np.zeros_like(values)
    for i in range(len(values)):
        # Gaussian curve size (sigma) is limited on the edges to avoid mismatch with downstream reaches
        local_sigma = min(sigma, (distances[i] - distances[0])*5.)  # hardcoded: 5 times the distance to the first point
        local_sigma = max(local_sigma, 10.)  # hardcoded: minimum standard deviation
        local_sigma_vec[i] = local_sigma
        # Compute Gaussian weights using norm.pdf
        weights = norm.pdf(distances, loc=distances[i], scale=uncertaintysigma)
        weights /= weights.sum()  # Normalize weights
        # Uncertainty is calculated from:
        # - the absolute value of the carving (how much carving is done)
        # - the difference between the elevation and surrounding elevations (how much slope there is).
        # A exponential transformation is applied to that 0 difference of elevation = 1. The slopefactor is added to put
        # more or less weight on the slope.
        # - The ratio between the carving and the differences between the elevations gives a measure of the uncertainty
        # relative to the slope
        # - Everything is multiplied by the weights from the Gaussian curve and summed to get the final uncertainty
        corrections = sum(np.abs(carving) * weights)**uncertaintyfactor
        if corrections < 1e-9:
            # If there is no carving, there are no smoothing to be made
            smoothed_values[i] = values[i]
            sd2 = None
        else:
            weightsslope = norm.pdf(distances, loc=distances[i], scale=slopesigma)
            weightsslope /= weightsslope.sum()  # Normalize weights
            deltaz = math.exp(sum(np.abs(values[i] - values) * weightsslope)) ** slopefactor
            uncertainty = corrections / deltaz
            uncertainty_vec[i] = uncertainty

            if i > 0:
                # In order to avoid the problem of the Gaussian curve being too wide, we need to make sure that the pdf of
                # the gaussian curve is lower than the previous one (on the left side of the previous one). Otherwise the
                # resulting elevation can be lower than the previous one, creating a non-hydraulically valid profile.
                x_values = distances[0:i - 1]
                mu1 = distances[i - 1]
                if sd2 is not None:
                    sd1 = sd2  # sd1 is the previous sd2
                    sd2 = uncertainty * local_sigma
                    mu2 = distances[i]
                    F1 = norm.pdf(x_values, loc=mu1, scale=sd1)
                    F2 = norm.pdf(x_values, loc=mu2, scale=sd2)
                    validpdf = np.all(F1 >= F2)
                    if not validpdf:
                        # The Gaussian curve is too wide, compared to the previous ones
                        # We need to reduce the standard deviation of the Gaussian curve in that case.
                        # We will use optimization to find the maximum possible standard deviation
                        restricted[i] = 1

                        def objective(tested_sd2):
                            """Objective function to minimize: we want the negative of sd2 for maximization"""
                            F1 = norm.pdf(x_values, loc=mu1, scale=sd1)
                            F2 = norm.pdf(x_values, loc=mu2, scale=tested_sd2)
                            diff = F1 - F2
                            if np.any(diff < 0):
                                return np.inf  # violates the constraint
                            return -tested_sd2  # maximize sd2

                        with warnings.catch_warnings():
                            warnings.filterwarnings("ignore", category=RuntimeWarning)
                            result = minimize_scalar(objective, bounds=(0.001, sd2), method='bounded')
                            if result.success:
                                sd2 = result.x
                            else:
                                # If optimization fails, the best guess is to use the previous sd
                                sd2 = sd1
                                restricted[i] = 2
                else:
                    # no sd2 computed, because there was no carving at the previous point
                    sd2 = uncertainty * local_sigma
            else:
                # First point, no previous point to compare
                sd2 = uncertainty * local_sigma

            sd2_vec[i] = sd2
            weights = norm.pdf(distances, loc=distances[i], scale=sd2)
            weights /= weights.sum()  # Normalize weights
            # Compute the weighted average
            smoothed_values[i] = np.sum(weights * values)

            # Final check: if the smoothed value is lower than the previous one, we set it to the previous one
            # (could not be the case after an area without corrections)
            if i > 0 and smoothed_values[i] < smoothed_values[i - 1]:
                smoothed_values[i] = smoothed_values[i - 1]
                restricted[i] = restricted[i]+10

    # Assign the smoothed values to the cross-sections
    i = 0
    for cs in listcs:
        cs.zws_smoothed = smoothed_values[i]
        cs.ws_uncertainty = uncertainty_vec[i]
        cs.restricted = restricted[i]
        cs.sd2 = sd2_vec[i]
        cs.local_sigma = local_sigma_vec[i]
        i +=1
    return


def rdp_simplify_and_resample(listcs, epsilon=0.03):
    """
    Simplify the cross-section list using Ramer-Douglas-Peucker algorithm,
    then resample back to the original number of points using linear interpolation.

    Parameters:
        listcs: List of cross-section objects
        epsilon: Tolerance for RDP algorithm (in elevation units)

    Returns:
        Modified listcs with resampled zws_quantilecarving values
    """
    # Extract distances and elevation values
    reachdist = 0
    distances = []
    values = []
    lastreach = None

    for cs in listcs:
        if lastreach is not None and cs.reach != lastreach:
            reachdist += lastreach.length
        distances.append(cs.dist + reachdist)
        values.append(cs.zws_quantilecarving)
        lastreach = cs.reach

    distances = np.array(distances)
    values = np.array(values)

    # Create points for RDP: [[x1, y1], [x2, y2], ...]
    points = np.column_stack((distances, values))

    # Apply RDP simplification
    simplified_points = rdp(points, epsilon=epsilon)

    # Extract simplified distances and values
    simplified_distances = simplified_points[:, 0]
    simplified_values = simplified_points[:, 1]

    # Create interpolation function from simplified points
    if len(simplified_distances) > 1:
        interp_func = interp1d(simplified_distances, simplified_values,
                               kind='linear', bounds_error=False,
                               fill_value='extrapolate')

        # Resample to original distances
        resampled_values = interp_func(distances)
    else:
        # If only one point remains, use its value for all
        resampled_values = np.full_like(values, simplified_values[0])

    # Update the zws_quantilecarving values in the cross-section objects
    for i, cs in enumerate(listcs):
        cs.zws_quantilecarving = resampled_values[i]

    return listcs


def execute_WSprocessing(network_shp, links_table, RID_field, order_field, datapoints, id_field_pts, RID_field_pts, Distance_field_pts, dem_forws_field, DEM_ID_field, output_points, messages, quantile=0.2, smooth_level=600 , uncertainty_sigma = 300, uncertainty_factor=0.85, slope_sigma=300, slope_factor=2.0, smoothing=True, rdp_epsilon=None):

    # The process:
    # - Removes bumps in the water surface profile following the quantile carving process of
    #   Schwanghart and Scherler (2017). See QuantileRegression.py for details.
    # - Simplifies the profile using Ramer-Douglas-Peucker algorithm, then resamples to original resolution
    # - Smooths the river profile. Smoothing is done with a Gaussian moving average, where the amount of smoothing (i.e.
    # the standard deviation of the gaussian curve), is parametered by the amount of correction done during the quantile
    # carving process and the local slope.


    network = RiverNetwork()
    network.dict_attr_fields['id'] = RID_field
    network.dict_attr_fields['order'] = order_field
    network.load_data(network_shp, links_table)

    collection = Points_collection(network, "data")
    collection.dict_attr_fields['id'] = id_field_pts
    collection.dict_attr_fields['reach_id'] = RID_field_pts
    collection.dict_attr_fields['dist'] = Distance_field_pts
    collection.dict_attr_fields['z_forws'] = dem_forws_field
    collection.dict_attr_fields['DEM_ID'] = DEM_ID_field
    collection.load_table(datapoints)

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
                QuantileCarving(list_cs, prevcs_list, messages, tau=quantile)
                # Apply RDP simplification and resampling
                if rdp_epsilon is not None:
                    rdp_simplify_and_resample(list_cs, epsilon=rdp_epsilon)
                if smoothing:
                    Gaussian_weighted_moving_average(list_cs, prevcs_list, smooth_level, uncertainty_sigma, uncertainty_factor, slope_sigma, slope_factor)
                list_cs = []
                prevcs_list = None
                restartdown = False
            prev_DEM_ID = cs.DEM_ID
            list_cs.append(cs)

            if isendreach and cs==endnode:
                QuantileCarving(list_cs, prevcs_list, messages, tau=quantile)
                # Apply RDP simplification and resampling
                if rdp_epsilon is not None:
                    rdp_simplify_and_resample(list_cs, epsilon=rdp_epsilon)
                if smoothing:
                    Gaussian_weighted_moving_average(list_cs, prevcs_list, smooth_level, uncertainty_sigma, uncertainty_factor, slope_sigma, slope_factor)
                list_cs = []
                prev_DEM_ID = None
                restartdown = True
            prev_cs = cs

    if smoothing:
        collection.add_SavedVariable("zws_smoothed", "float")
        #collection.add_SavedVariable("ws_uncertainty", "float")
        #collection.add_SavedVariable("restricted", "float")
        #collection.add_SavedVariable("sd2", "float")
        #collection.add_SavedVariable("local_sigma", "float")
    collection.add_SavedVariable("zws_quantilecarving", "float")

    collection.save_points(output_points)

    return
