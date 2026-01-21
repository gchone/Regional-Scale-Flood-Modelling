# -*- coding: utf-8 -*-

# Author: Mariana
"""This tool creates a 'near table' to relate river routes('A') and D8/D4 routes ('B').
When it runs once, some links are omitted and others in_features are linked to two different reaches from the near_feature layer.
This issue is related to the way ArcGis calculates distance in proximity tools such as "Near Table"
- Multiple features may be equally closest to another feature. When this occurs, one of the equally closest features is randomly selected as the closest.
- The distance between two features is zero whenever there is at least one x,y coordinate that is shared between them.
- This means that when two features intersect, overlap, cross, or touch, the distance between them is zero.
For fixing this issue, the tool has to run twice (A to B and B to A). Then 2 clean-ups are required:
1. Clean up of duplicate combinations
2. Clean up wrong combination based on the number of intersections (points) between the two layers"""

# 1. Running Generate Near Table in both directions
import os.path
import numpy as np
import arcpy
import ArcpyGarbageCollector as gc


def execute_RelateNetworks(shapefile_A, RID_A, shapefile_B, RID_B, out_table, messages):


    resultA = arcpy.GetCount_management(shapefile_A)
    resultB = arcpy.GetCount_management(shapefile_B)
    countA = int(resultA.getOutput(0))
    countB = int(resultB.getOutput(0))


    if countA != countB:
        arcpy.AddError("The feature classes have different number of rows. This tool runs when row value is equal")

    else:

        # Intersection between the two line shapefiles and counting the points of the intersection.
        to_intersect = [shapefile_A, shapefile_B]
        temp_intersect = gc.CreateScratchName("temp", data_type="FeatureClass", workspace="in_memory")
        arcpy.Intersect_analysis(to_intersect, temp_intersect, "ALL", "", "POINT")
        # "PART_COUNT" provides de amount of points in each intersection between the two line shapefiles. Analyzing this
        # value allows to choose the correct combination in the near_table (temp_merged). If we have a combination like
        # 5-8 with a part_count=1 (being the 5 the # routeID and 8 the RID) and 5-10 with a part_count = 256, the last
        # combination is the correct one.
        arcpy.AddGeometryAttributes_management(temp_intersect, "PART_COUNT")
        B_fields = [f.name for f in arcpy.Describe(shapefile_B).fields]
        RID_B_index = B_fields.index(RID_B)
        inter_RID_B_index = len(arcpy.Describe(shapefile_A).fields)+RID_B_index
        inter_fields = [f.name for f in arcpy.Describe(temp_intersect).fields]
        inter_RID_B = inter_fields[inter_RID_B_index]
        numpyrelatetable = arcpy.da.FeatureClassToNumPyArray(temp_intersect, [RID_A, inter_RID_B, "PART_COUNT"])

        # Combinations of RID with the highest PART_COUNT should be kept.
        uniques_RIDs = np.unique(numpyrelatetable[[RID_A]])
        filtered_RIDA = None
        for i in uniques_RIDs:
            tmp = numpyrelatetable[np.where(numpyrelatetable[[RID_A]] == i)]
            tmp_max = np.max(tmp["PART_COUNT"])
            tmp_res = tmp[tmp["PART_COUNT"] == tmp_max]
            if filtered_RIDA is None:
                filtered_RIDA = np.copy(tmp_res)
            else:
                filtered_RIDA = np.concatenate((filtered_RIDA, tmp_res))

        uniques_RIDs = np.unique(filtered_RIDA[[RID_B]])
        filtered_RIDB = None
        for i in uniques_RIDs:
            tmp = filtered_RIDA[np.where(filtered_RIDA[[RID_B]] == i)]
            tmp_max = np.max(tmp["PART_COUNT"])
            tmp_res = tmp[tmp["PART_COUNT"] == tmp_max]
            if filtered_RIDB is None:
                filtered_RIDB = np.copy(tmp_res)
            else:
                filtered_RIDB = np.concatenate((filtered_RIDB, tmp_res))

        arcpy.da.NumPyArrayToTable(filtered_RIDB, out_table)

        #Check if the matches are always one-to-one
        uniques_RID1 = np.unique(filtered_RIDB[[RID_A]])
        uniques_RID2 = np.unique(filtered_RIDB[[RID_B]])
        if len(uniques_RID1)!=filtered_RIDB.shape[0] or len(uniques_RID2)!=filtered_RIDB.shape[0]:
            messages.addWarningMessage("Incorrect network match")
