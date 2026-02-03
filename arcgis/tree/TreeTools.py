# -*- coding: utf-8 -*-


# ArcGIS tools for tree manipulation
import arcpy

from tree.RiverNetwork import *
from RasterIO import *
import ArcpyGarbageCollector as gc
from collections import Counter

def execute_TreeFromFlowDir(r_flowdir, str_frompoints, route_shapefile, routelinks_table, routeID_field, str_output_points, messages, split_pts=None, tolerance=None):
    """
    Create a tree structure following the Flow Direction from the From points.

    :param r_flowdir: Flow direction raster
    :param str_frompoints: Upstream ends of the network (shapefile of points)
    :param route_shapefile: Output shapefile
    :param routelinks_table: Output table providing the links between reaches
    :param routeID_field: Name of the reach ID field
    :param str_output_points: Output table of the Flow direction pixels along the flow path
    :param messages: ArcGIS Message object
    :return: None
    """

    flowdir = RasterIO(r_flowdir)

    segmentid = 0
    pointid = 0

    # create the links table as a numpy array
    links = np.empty(0, dtype=[(RiverNetwork.reaches_linkfielddown, 'i4'), (RiverNetwork.reaches_linkfieldup, 'i4')])

    # For efficiency, the points table is managed as a numpy array (and latter converted into a table)
    pointstype = [("id", 'i4'), ("RID", 'i4'), ("dist", 'f8'), ("offset", 'f8'), ("X", 'f8'), ("Y", 'f8'), ("row", 'i4'), ("col", 'i4')]
    pointsarray = np.empty(0, dtype=pointstype)

    # this dict is used to stored the point downstream of each reach (first point to use when building the river lines)
    initialpoint = {}

    # this dict is used to stored the original Frompoint OID for upstream reaches
    original_fp_OID = {}

    loop_error = False

    try:
        # Starting at each From point
        frompointcursor = arcpy.da.SearchCursor(str_frompoints, ["SHAPE@", "OID@"])
        for frompoint in frompointcursor:

            # Point Shape
            frompointshape = frompoint[0].firstPoint

            # Converting coordinates
            currentcol = flowdir.XtoCol(frompointshape.X)
            currentrow = flowdir.YtoRow(frompointshape.Y)

            # Security check to make sure the From point is inside the Flow dir raster
            intheraster = True
            if currentcol < 0 or currentcol >= flowdir.raster.width or currentrow < 0 or currentrow >= flowdir.raster.height:
                intheraster = False
            elif (flowdir.getValue(currentrow, currentcol) != 1 and flowdir.getValue(currentrow, currentcol) != 2 and
                          flowdir.getValue(currentrow, currentcol) != 4 and flowdir.getValue(currentrow,
                                                                                             currentcol) != 8 and
                          flowdir.getValue(currentrow, currentcol) != 16 and flowdir.getValue(currentrow,
                                                                                              currentcol) != 32 and flowdir.getValue(
                currentrow, currentcol) != 64 and flowdir.getValue(currentrow, currentcol) != 128):
                intheraster = False


            # Check if the new points coordinates (in row, column) are already in the points numpy array
            checkrow = pointsarray["row"] == currentrow
            checkcol = pointsarray["col"] == currentcol
            checkpoint = np.extract(np.logical_and(checkrow, checkcol), pointsarray)
            if len(checkpoint) > 0:
                intheraster = False
                messages.addWarningMessage("From point "+str(frompoint[1])+" already on flow path")

            segmentid += 1
            totaldist = 0

            # For efficiency, points are only added to the pointsarray by batch. They are temporary stored as a list of list
            #  witch each point is formatted as a list [id, RID, dist, offset, X, Y, row, column]
            pointslist = []

            # For each point encountered along the flow path
            while (intheraster):

                # Add the point to the list
                pointid += 1
                pointslist.append([pointid, segmentid, totaldist, 0, flowdir.ColtoX(currentcol), flowdir.RowtoY(currentrow), currentrow, currentcol])

                # Look for the next point
                direction = flowdir.getValue(currentrow, currentcol)
                if (direction == 1):
                    currentcol = currentcol + 1
                    currentdistance = flowdir.raster.meanCellWidth
                if (direction == 2):
                    currentcol = currentcol + 1
                    currentrow = currentrow + 1
                    currentdistance = math.sqrt(
                        flowdir.raster.meanCellWidth * flowdir.raster.meanCellWidth + flowdir.raster.meanCellHeight * flowdir.raster.meanCellHeight)
                if (direction == 4):
                    currentrow = currentrow + 1
                    currentdistance = flowdir.raster.meanCellHeight
                if (direction == 8):
                    currentcol = currentcol - 1
                    currentrow = currentrow + 1
                    currentdistance = math.sqrt(
                        flowdir.raster.meanCellWidth * flowdir.raster.meanCellWidth + flowdir.raster.meanCellHeight * flowdir.raster.meanCellHeight)
                if (direction == 16):
                    currentcol = currentcol - 1
                    currentdistance = flowdir.raster.meanCellWidth
                if (direction == 32):
                    currentcol = currentcol - 1
                    currentrow = currentrow - 1
                    currentdistance = math.sqrt(
                        flowdir.raster.meanCellWidth * flowdir.raster.meanCellWidth + flowdir.raster.meanCellHeight * flowdir.raster.meanCellHeight)
                if (direction == 64):
                    currentrow = currentrow - 1
                    currentdistance = flowdir.raster.meanCellHeight
                if (direction == 128):
                    currentcol = currentcol + 1
                    currentrow = currentrow - 1
                    currentdistance = math.sqrt(
                        flowdir.raster.meanCellWidth * flowdir.raster.meanCellWidth + flowdir.raster.meanCellHeight * flowdir.raster.meanCellHeight)



                # Security check to make sure the point is still inside the Flow dir raster
                if currentcol < 0 or currentcol >= flowdir.raster.width or currentrow < 0 or currentrow >= flowdir.raster.height:
                    intheraster = False
                elif (flowdir.getValue(currentrow, currentcol) != 1 and flowdir.getValue(currentrow,
                                                                                         currentcol) != 2 and
                              flowdir.getValue(currentrow, currentcol) != 4 and flowdir.getValue(currentrow,
                                                                                                 currentcol) != 8 and
                              flowdir.getValue(currentrow, currentcol) != 16 and flowdir.getValue(currentrow,
                                                                                                  currentcol) != 32 and flowdir.getValue(
                    currentrow, currentcol) != 64 and flowdir.getValue(currentrow, currentcol) != 128):
                    intheraster = False

                if intheraster:
                    totaldist += currentdistance

                    # Check if the new point coordinates (in row, column) are already in the pointslist
                    coordlist = [(item[6], item[7]) for item in pointslist]
                    if (currentrow, currentcol) in coordlist:
                        intheraster = False
                        messages.addWarningMessage("Infinite loop found at "+str(flowdir.ColtoX(currentcol))+";"+str(flowdir.RowtoY(currentrow)))
                        pointslisttuple = []
                        for point in pointslist:
                            pointslisttuple.append((point[0], point[1], totaldist - point[2], point[3], point[4],
                                                    point[5], point[6], point[7]))

                        pointsarray = np.append(pointsarray, np.array(pointslisttuple, dtype=pointstype))
                        loop_error = True
                    else:

                        # Check if the new points coordinates (in row, column) are already in the points numpy array
                        checkrow = pointsarray["row"] == currentrow
                        checkcol = pointsarray["col"] == currentcol
                        checkpoint = np.extract(np.logical_and(checkrow, checkcol), pointsarray)

                        if len(checkpoint) > 0:

                            confluencepoint = checkpoint[0]
                            # A confluence with a previously treated flow path is met
                            # The reach that is met is split in two
                            # A new RID is assigned to the upstream part of this reach
                            matchingrid = pointsarray["RID"] == confluencepoint["RID"]
                            matchingdist = pointsarray["dist"] > confluencepoint["dist"]

                            len_of_upstream_meet_reach = len(pointsarray[np.logical_and(matchingrid, matchingdist)])

                            if len_of_upstream_meet_reach > 0:
                                pointsarray["RID"][np.logical_and(matchingrid, matchingdist)] = segmentid + 1
                                pointsarray["dist"][np.logical_and(matchingrid, matchingdist)] = pointsarray["dist"][np.logical_and(matchingrid, matchingdist)] - confluencepoint["dist"]
                                # The link table need to be updated too (new RID for the upstream part of the met reach)
                                links[RiverNetwork.reaches_linkfielddown][links[RiverNetwork.reaches_linkfielddown] == confluencepoint["RID"]] = segmentid + 1
                            else:
                                # special case: the flow meet another reach from it's start point
                                messages.addWarningMessage("Reach " + str(segmentid) + " encountered another From point")

                            # Adding the pointslist to the pointsarray
                            #   but first, the distance value must be reverse (it was computed backward. It must be from downstream to upstream), and the points must be tuples
                            pointslisttuple = []
                            for point in pointslist:
                                pointslisttuple.append((point[0], point[1], totaldist - point[2], point[3], point[4], point[5], point[6], point[7]))

                            pointsarray = np.append(pointsarray, np.array(pointslisttuple, dtype=pointstype))

                            # Adding the confluence info in the link table
                            if len_of_upstream_meet_reach > 0:
                                to_add = numpy.empty(2, dtype=links.dtype)
                                to_add[RiverNetwork.reaches_linkfielddown] = confluencepoint["RID"]
                                to_add[RiverNetwork.reaches_linkfieldup][0] = segmentid
                                to_add[RiverNetwork.reaches_linkfieldup][1] = segmentid + 1
                            else:
                                to_add = numpy.empty(1, dtype=links.dtype)
                                to_add[RiverNetwork.reaches_linkfielddown] = confluencepoint["RID"]
                                to_add[RiverNetwork.reaches_linkfieldup] = segmentid
                            links = numpy.append(links, to_add)

                            # Storing the downstream point of the upstream reach
                            initialpoint[segmentid] = arcpy.Point(float(confluencepoint["X"]), float(confluencepoint["Y"]))
                            initialpoint[segmentid + 1] = arcpy.Point(float(confluencepoint["X"]), float(confluencepoint["Y"]))

                            # Updating the segment id - Frompoint OID dict
                            original_fp_OID[segmentid] = frompoint[1]
                            if confluencepoint["RID"] in original_fp_OID:
                                original_fp_OID[segmentid + 1] = original_fp_OID.pop(confluencepoint["RID"])

                            segmentid += 1
                            intheraster = False
                else:
                    # Adding the pointslist to the pointsarray
                    #   but first, the distance value must be reverse (it was computed backward. It must be from downstream to upstream), and the points must be tuples
                    pointslisttuple = []
                    for point in pointslist:
                        pointslisttuple.append((point[0], point[1], totaldist - point[2], point[3], point[4], point[5], point[6], point[7]))
                    pointsarray = np.append(pointsarray, np.array(pointslisttuple, dtype=pointstype))

                    original_fp_OID[segmentid] = frompoint[1]

        points_table = gc.CreateScratchName("pts", data_type="ArcInfoTable", workspace="in_memory")
        arcpy.da.NumPyArrayToTable(pointsarray, points_table)

        if not loop_error:
            #Splitting lines if necessary
            if split_pts is not None:
                # a temp file of the points is necessary, to do a spatial join
                #pts_table = gc.CreateScratchName("pts_table", data_type="ArcInfoTable", workspace=arcpy.env.scratchWorkspace)
                #arcpy.da.NumPyArrayToTable(pointsarray, pts_table)

                points_shp = gc.CreateScratchName("pts", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
                arcpy.MakeXYEventLayer_management(points_table, "X", "Y", "pts_layer", spatial_reference=str_frompoints)
                arcpy.CopyFeatures_management("pts_layer", points_shp)

                #gc.CleanTempFile(pts_table)
                join_split = gc.CreateScratchName("pts_join", data_type="FeatureClass", workspace="in_memory")
                arcpy.SpatialJoin_analysis(split_pts, points_shp, join_split, match_option="CLOSEST", join_type="KEEP_COMMON", search_radius=tolerance)
                arcpy.DeleteIdentical_management(join_split, "id") # If two split points are too close, the split point on the D8 path is the same
                gc.CleanTempFile(points_shp)
                join_split2 = gc.CreateScratchName("pts_join", data_type="FeatureClass", workspace="in_memory")
                arcpy.Sort_management(join_split, join_split2, [["dist", "DESCENDING"]])
                join_split_cursor = arcpy.da.SearchCursor(join_split2, ["RID", "dist", "X", "Y"])
                for split in join_split_cursor:
                    # for every split pts, update the RID upstream for the points
                    segmentid +=1
                    matchingrid = pointsarray["RID"] == split[0]
                    matchingdist = pointsarray["dist"] > split[1]
                    pointsarray["RID"][np.logical_and(matchingrid, matchingdist)] = segmentid
                    pointsarray["dist"][np.logical_and(matchingrid, matchingdist)] = pointsarray["dist"][np.logical_and(matchingrid, matchingdist)] - split[1]
                    # update the links
                    links[RiverNetwork.reaches_linkfielddown][links[RiverNetwork.reaches_linkfielddown] == split[0]] = segmentid
                    to_add = numpy.empty(1, dtype=links.dtype)
                    to_add[RiverNetwork.reaches_linkfielddown] = split[0]
                    to_add[RiverNetwork.reaches_linkfieldup] = segmentid
                    links = numpy.append(links, to_add)
                    # add initial line points
                    initialpoint[segmentid] = arcpy.Point(split[2], split[3])
                    # update the fp_id
                    if split[0] in original_fp_OID:
                        original_fp_OID[segmentid] = original_fp_OID.pop(split[0])

        # Saving the points
        if arcpy.Exists(str_output_points) and arcpy.env.overwriteOutput == True:
            arcpy.Delete_management(str_output_points)
        arcpy.da.NumPyArrayToTable(pointsarray, str_output_points)

        if not loop_error:
            # Saving the links
            if arcpy.Exists(routelinks_table) and arcpy.env.overwriteOutput == True:
                arcpy.Delete_management(routelinks_table)
            arcpy.da.NumPyArrayToTable(links, routelinks_table)


            # Creating lines
            arcpy.CreateFeatureclass_management("in_memory", "LINES", "POLYLINE", spatial_reference=str_frompoints)
            lines = "in_memory\LINES"
            arcpy.AddField_management(lines, routeID_field, "LONG")
            arcpy.AddField_management(lines, "ORIG_FID", "LONG")
            linecursor = arcpy.da.InsertCursor(lines, ["SHAPE@", routeID_field, "ORIG_FID"])
            reachidlist = set(pointsarray["RID"])
            for reachid in reachidlist:
                # New line
                vertices = arcpy.Array()
                points = np.sort(pointsarray[pointsarray["RID"] == reachid], order="dist")
                # Add the downstream point if it exists
                if reachid in initialpoint.keys():
                    vertices.add(initialpoint[reachid])
                for point in points:
                    vertices.add(arcpy.Point(float(point["X"]), float(point["Y"])))
                line = arcpy.Polyline(vertices)
                if reachid in original_fp_OID:
                    linecursor.insertRow([line, reachid, original_fp_OID[reachid]])
                else:
                    linecursor.insertRow([line, reachid, -999])


            # Create routes from start point to end point
            arcpy.AddField_management(lines, routeID_field, "LONG")
            arcpy.AddField_management(lines, "FromF", "FLOAT")
            arcpy.CalculateField_management(lines, "FromF", "0", "PYTHON")
            arcpy.AddField_management(lines, "LENGTH", "DOUBLE")
            arcpy.CalculateField_management(lines, "LENGTH", "!shape.length!", "PYTHON")
            Lengthfield = "LENGTH"

            arcpy.CreateRoutes_lr(lines, routeID_field, route_shapefile, "TWO_FIELDS",
                                     from_measure_field="FromF",
                                     to_measure_field=Lengthfield)
            arcpy.JoinField_management(route_shapefile, routeID_field, lines, routeID_field, "ORIG_FID")

    finally:
        gc.CleanAllTempFiles()

def execute_CreateTreeFromShapefile(rivernet, route_shapefile, routelinks_table, routeID_field, downstream_reach_field, messages, channeltype_field = None):
    """
    Create the river network data structure from a shapefile of lines
    :param rivernet: input shapefile
    :param route_shapefile: output shapefile
    :param routelinks_table: output table providing the links between reaches
    :param routeID_field: name of the reach ID field
    :param downstream_reach_field: name of the field identifying the most downstream reach (value = 1 or 0)
    :param messages: ArcGIS Message object
    :param channeltype_field: Field identifying the main channel (value = 1) or a secondary channel (value = 0)
    :return: None
    """



    def __recursivebuildtree(downstream_junction, np_junctions, routeID_field, list_down_up_links, channeltype_field, reaches_done):

        if downstream_junction["ENDTYPE"] == "End":
            # The line should be flipped
            expression = routeID_field + " = " + str(downstream_junction[routeID_field])
            arcpy.SelectLayerByAttribute_management("netlyr", "ADD_TO_SELECTION", expression)

        reaches_done.append(downstream_junction[routeID_field])

        # Find the upstream junction for the current reach
        condition1 = np_junctions[routeID_field] == downstream_junction[routeID_field]
        condition2 = np_junctions["FEAT_SEQ"] != downstream_junction["FEAT_SEQ"]
        current_upstream_junction = np.extract(np.logical_and(condition1, condition2), np_junctions)[0]

        # Find other junctions at the same place
        condition1 = np_junctions["FEAT_SEQ"] == current_upstream_junction["FEAT_SEQ"]
        condition2 = np_junctions[routeID_field] != current_upstream_junction[routeID_field]

        other_upstream_junctions = np.extract(np.logical_and(condition1, condition2), np_junctions)
        # if there are secondary channels, they must be treated before the main channels,
        #  but with recursion stop when meeting a main channel back
        if channeltype_field is not None:
            other_upstream_junctions = np.sort(other_upstream_junctions, order=channeltype_field)

        for upstream_junction in other_upstream_junctions:

            if channeltype_field is None \
                    or (not (downstream_junction[channeltype_field] == 0 and upstream_junction[channeltype_field] == 1) \
                        and not upstream_junction[routeID_field] in reaches_done):
                # Add a row in the links table
                list_down_up_links.append((downstream_junction[routeID_field], upstream_junction[routeID_field]))
                # Apply recursively
                __recursivebuildtree(upstream_junction, np_junctions, routeID_field, list_down_up_links, channeltype_field, reaches_done)

        return


    try:



        # Create Junction points: two points created by reach, at both end of the line
        # (done separately with "END" and "START", rather than with "BOTH_ENDS", to keep track of what point is at which extremity)
        with arcpy.EnvManager(outputMFlag="Disabled"):
            with arcpy.EnvManager(outputZFlag="Disabled"):
                # Do not included Z and M values in the points, as it will mess with the grouping by Shape step (it should only be based on X and Y position)
                junctions_end = gc.CreateScratchName("net", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
                arcpy.FeatureVerticesToPoints_management(rivernet, junctions_end, "END")
                junctions_start = gc.CreateScratchName("net", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
                arcpy.FeatureVerticesToPoints_management(rivernet, junctions_start, "START")
        arcpy.AddField_management(junctions_end, "ENDTYPE", "TEXT", field_length=10)
        arcpy.AddField_management(junctions_start, "ENDTYPE", "TEXT", field_length=10)
        arcpy.CalculateField_management(junctions_end, "ENDTYPE", "'End'", "PYTHON")
        arcpy.CalculateField_management(junctions_start, "ENDTYPE", "'Start'", "PYTHON")
        junctions = gc.CreateScratchName("net", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
        arcpy.Merge_management([junctions_end, junctions_start], junctions)
        junctionid_name = arcpy.Describe(junctions).OIDFieldName

        # Add a id ("FEAT_SEQ") to the junction grouping junctions at the same place (same place = same id))
        junctions_table = gc.CreateScratchName("table", data_type="ArcInfoTable", workspace=arcpy.env.scratchWorkspace)
        arcpy.FindIdentical_management(junctions, junctions_table, ["Shape"])
        arcpy.JoinField_management(junctions, junctionid_name, junctions_table, "IN_FID")
        # Add also the rivernet data into the junctions files (make the query to treat the main channel in priority easier after)
        arcpy.JoinField_management(junctions, routeID_field, rivernet, routeID_field)




        # get the attribute tables
        if channeltype_field is not None:
            #np_net = arcpy.da.FeatureClassToNumPyArray(rivernet, [routeID_field, downstream_reach_field, channeltype_field])
            np_junctions = arcpy.da.FeatureClassToNumPyArray(junctions,
                                                             [junctionid_name, routeID_field, "FEAT_SEQ", "ENDTYPE",
                                                              downstream_reach_field, channeltype_field])
        else:
            #np_net = arcpy.da.FeatureClassToNumPyArray(rivernet, [routeID_field, downstream_reach_field])
            np_junctions = arcpy.da.FeatureClassToNumPyArray(junctions,
                                                             [junctionid_name, routeID_field, "FEAT_SEQ", "ENDTYPE",
                                                              downstream_reach_field])

        # Find downstream ends
        # count the number of junctions at the same place
        u, indices, count = np.unique(np_junctions["FEAT_SEQ"], return_index=True, return_counts=True)
        # select only the ones with one junction only
        condition = np.array([item in u[count == 1] for item in np_junctions["FEAT_SEQ"]])
        # select only the junctions for the downstream reachs
        ## get a list of id of downstream reaches
        #net_down_id = np.extract(np_net[downstream_reach_field] == 1, np_net)[routeID_field]
        ## select only the junction from this list
        #condition2 = np.array([item in net_down_id for item in np_junctions[routeID_field]])
        condition2 = np_junctions[downstream_reach_field] == 1
        downstream_junctions = np.extract(np.logical_and(condition, condition2), np_junctions)

        # Make a layer from a copy of the feature class (used for flipping lines)
        rivernetcopy = gc.CreateScratchName("net", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
        arcpy.CopyFeatures_management(rivernet, rivernetcopy)
        arcpy.MakeFeatureLayer_management(rivernetcopy, "netlyr")
        arcpy.SelectLayerByAttribute_management("netlyr", "CLEAR_SELECTION")

        # Do the job recursively
        list_down_up_links = []
        # list to keep track of what's done (used to avoid going in loops if there's any)
        reaches_done = []
        for downstream_junction in downstream_junctions:
            __recursivebuildtree(downstream_junction, np_junctions, routeID_field, list_down_up_links, channeltype_field, reaches_done)

        # Create the links table
        if arcpy.Exists(routelinks_table) and arcpy.env.overwriteOutput == True:
            arcpy.Delete_management(routelinks_table)
        arcpy.CreateTable_management(os.path.dirname(routelinks_table), os.path.basename(routelinks_table))
        arcpy.AddField_management(routelinks_table, RiverNetwork.reaches_linkfielddown, "LONG")
        arcpy.AddField_management(routelinks_table, RiverNetwork.reaches_linkfieldup, "LONG")
        if arcpy.Describe(os.path.dirname(routelinks_table)).dataType == "Folder":
            # ArcGIS create a "Field1" field by default for tables in folder
            arcpy.DeleteField_management(routelinks_table, "Field1")
        # Add info into the links table
        linkcursor = arcpy.da.InsertCursor(routelinks_table,
                                           [RiverNetwork.reaches_linkfielddown, RiverNetwork.reaches_linkfieldup])
        for link_row in list_down_up_links:
            linkcursor.insertRow(link_row)

        # Flip the wrongly orientated lines
        if arcpy.Describe("netlyr").FIDSet != "": # There is a selection
            arcpy.FlipLine_edit("netlyr")

        # Create routes from start point to end point
        arcpy.AddField_management(rivernetcopy, "FromF", "FLOAT")
        arcpy.CalculateField_management(rivernetcopy, "FromF", "0", "PYTHON")
        if arcpy.Describe(arcpy.env.scratchWorkspace).dataType=="Folder":
            # if the scrach workspace is a folder, the copy of the river network is a shapefile (else, it's within a
            # File geodatabase and already has a Length field)
            #arcpy.AddGeometryAttributes_management(rivernetcopy, "LENGTH") # "LENGTH" is not an available option and I can't get why
            arcpy.AddField_management(rivernetcopy, "LENGTH", "DOUBLE")
            arcpy.CalculateField_management(rivernetcopy, "LENGTH", "!shape.length!", "PYTHON")
            #arcpy.CalculateGeometryAttributes_management(rivernetcopy, [["LENGTH", "LENGTH"]])
            Lengthfield = "LENGTH"
        else:
            Lengthfield = "SHAPE_LENGTH"

        arcpy.CreateRoutes_lr(rivernetcopy, routeID_field, route_shapefile, "TWO_FIELDS",
                                 from_measure_field="FromF",
                                 to_measure_field=Lengthfield)
        if channeltype_field is not None:
            arcpy.JoinField_management(route_shapefile, routeID_field, rivernet, routeID_field, channeltype_field)

    finally:
        gc.CleanAllTempFiles()


def createFullTreeTableFromShapefile(route_shapefile, routeID_field, IDlink1name, IDlink2name, IDlink_orientationname):
    """
    Return the full network numpy array table. It's similar to execute_CreateTreeFromShapefile, but it doesn't save the
    results on file. The resulting network is not oriented (there's links, but without indication of what is upstream or
    downstream
    """



    def __recursivebuildtree(RID, np_junctions, routeID_field, list_down_up_links, reaches_done):

        reaches_done.append(RID)


        # Find the END junction for the current reach
        condition1 = np_junctions["ENDTYPE"] == "End"
        condition2 = np_junctions[routeID_field] == RID
        current_upstream_junction = np.extract(np.logical_and(condition1, condition2), np_junctions)[0]

        # Find other junctions at the same place
        condition1 = np_junctions["FEAT_SEQ"] == current_upstream_junction["FEAT_SEQ"]
        condition2 = np_junctions[routeID_field] != current_upstream_junction[routeID_field]

        other_upstream_junctions = np.extract(np.logical_and(condition1, condition2), np_junctions)

        for junction in other_upstream_junctions:
            # reaches_done is the list of reaches with all junctions, upstream and downstream, checked.
            # we must also look into list_down_up_links, as some links could be already added before the next reach is in reaches_done

            # Add a row in the links table
            if junction["ENDTYPE"] == "Start":
                if not (((junction[routeID_field], RID, "START-TO-END") in list_down_up_links) or ((RID, junction[routeID_field], "END-TO-START") in list_down_up_links)):
                    list_down_up_links.append((RID, junction[routeID_field], "END-TO-START"))
            else:
                if not (((junction[routeID_field], RID, "END-TO-END") in list_down_up_links) or ((RID, junction[routeID_field], "END-TO-END") in list_down_up_links)):
                    list_down_up_links.append((RID, junction[routeID_field], "END-TO-END"))

            if junction[routeID_field] not in reaches_done:
                # Apply recursively
                __recursivebuildtree(junction[routeID_field], np_junctions, routeID_field, list_down_up_links,
                                     reaches_done)



        # Find the START junction for the current reach
        condition1 = np_junctions["ENDTYPE"] == "Start"
        condition2 = np_junctions[routeID_field] == RID
        current_upstream_junction = np.extract(np.logical_and(condition1, condition2), np_junctions)[0]

        # Find other junctions at the same place
        condition1 = np_junctions["FEAT_SEQ"] == current_upstream_junction["FEAT_SEQ"]
        condition2 = np_junctions[routeID_field] != current_upstream_junction[routeID_field]

        other_upstream_junctions = np.extract(np.logical_and(condition1, condition2), np_junctions)

        for junction in other_upstream_junctions:

            # Add a row in the links table
            if junction["ENDTYPE"] == "Start":
                if not (((junction[routeID_field], RID, "START-TO-START") in list_down_up_links) or ((RID, junction[routeID_field], "START-TO-START") in list_down_up_links)):
                    list_down_up_links.append((RID, junction[routeID_field], "START-TO-START"))
            else:
                if not (((junction[routeID_field], RID, "END-TO-START") in list_down_up_links) or ((RID, junction[routeID_field], "START-TO-END") in list_down_up_links)):
                    list_down_up_links.append((RID, junction[routeID_field], "START-TO-END"))

            if junction[routeID_field] not in reaches_done:
                __recursivebuildtree(junction[routeID_field], np_junctions, routeID_field, list_down_up_links,
                                     reaches_done)

    try:



        # Create Junction points: two points created by reach, at both end of the line
        # (done separately with "END" and "START", rather than with "BOTH_ENDS", to keep track of what point is at which extremity)
        with arcpy.EnvManager(outputMFlag="Disabled"):
            with arcpy.EnvManager(outputZFlag="Disabled"):
                # Do not included Z and M values in the points, as it will mess with the grouping by Shape step (it should only be based on X and Y position)
                junctions_end = gc.CreateScratchName("net", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
                arcpy.FeatureVerticesToPoints_management(route_shapefile, junctions_end, "END")
                junctions_start = gc.CreateScratchName("net", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
                arcpy.FeatureVerticesToPoints_management(route_shapefile, junctions_start, "START")
        arcpy.AddField_management(junctions_end, "ENDTYPE", "TEXT", field_length=10)
        arcpy.AddField_management(junctions_start, "ENDTYPE", "TEXT", field_length=10)
        arcpy.CalculateField_management(junctions_end, "ENDTYPE", "'End'", "PYTHON")
        arcpy.CalculateField_management(junctions_start, "ENDTYPE", "'Start'", "PYTHON")
        junctions = gc.CreateScratchName("net", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
        arcpy.Merge_management([junctions_end, junctions_start], junctions)
        junctionid_name = arcpy.Describe(junctions).OIDFieldName

        # Add a id ("FEAT_SEQ") to the junction grouping junctions at the same place (same place = same id))
        junctions_table = gc.CreateScratchName("table", data_type="ArcInfoTable", workspace=arcpy.env.scratchWorkspace)
        arcpy.FindIdentical_management(junctions, junctions_table, ["Shape"])
        arcpy.JoinField_management(junctions, junctionid_name, junctions_table, "IN_FID")
        # Add also the rivernet data into the junctions files (make the query to treat the main channel in priority easier after)
        arcpy.JoinField_management(junctions, routeID_field, route_shapefile, routeID_field)


        np_net = arcpy.da.FeatureClassToNumPyArray(route_shapefile, [routeID_field])
        np_junctions = arcpy.da.FeatureClassToNumPyArray(junctions,
                                                         [junctionid_name, routeID_field, "FEAT_SEQ", "ENDTYPE"])

        list_down_up_links = []
        # lists to keep track of what's done (used to avoid going in loops if there's any)
        reaches_done = []


        # Instead of starting at the downstream reach, we can start at a random one and flag the ones we have processed
        # This is included in a loop just in case there are several unlinked networks.

        for reach in np_net:
            if reach[routeID_field] not in reaches_done:
                __recursivebuildtree(reach[routeID_field], np_junctions, routeID_field, list_down_up_links, reaches_done)


        dt = [(IDlink1name, "i8"), (IDlink2name, "i8"), (IDlink_orientationname, "U15")]
        return np.array(list_down_up_links, dtype=dt)

    finally:
        gc.CleanAllTempFiles()

def execute_CreateFromPointsAndSplits(network_shp, links_table, RID_field, points, splits):

    network = RiverNetwork()
    network.dict_attr_fields['id'] = RID_field
    network.load_data(network_shp, links_table)

    arcpy.CreateFeatureclass_management(os.path.dirname(points), os.path.basename(points), "POINT", spatial_reference=network.SpatialReference)
    arcpy.AddField_management(points, network.dict_attr_fields["id"], "LONG")
    arcpy.CreateFeatureclass_management(os.path.dirname(splits), os.path.basename(splits), "POINT",
                                        spatial_reference=network.SpatialReference)

    insertfp = arcpy.da.InsertCursor(points, [network.dict_attr_fields["id"], 'SHAPE@'])
    for reach in network.browse_reaches_down_to_up():
        if reach.is_upstream_end():
            insertfp.insertRow([reach.id, reach.shape.getPart(0)[-1]])
    del insertfp

    insertsplits = arcpy.da.InsertCursor(splits, ['SHAPE@'])
    for reach in network.browse_reaches_down_to_up():
        if not reach.is_upstream_end() and len(list(reach.get_uptream_reaches())) == 1:
            insertsplits.insertRow([reach.shape.getPart(0)[-1]])
    del insertsplits

def execute_CheckNetFitFromUpStream(routes_A, links_A, RID_A, routes_B, links_B, RID_B, frompoints, matching_table, messages, final_selection="BEST_FIT"):
    # final_selection = "BEST_FIT": in case of topological differences, the result is the most often found match (with ties resolved by closeness).
    # final_selection = "ENDS": in case of topological differences, the result is the path corresponding to the upstream segment match.

    # refD8_net needs an ORIG_FID attribute: the FID of the Frompoint file use
    refD8_net = RiverNetwork()
    refD8_net.dict_attr_fields['id'] = RID_A
    refD8_net.dict_attr_fields['ORIG_FID'] = "ORIG_FID"
    refD8_net.load_data(routes_A, links_A)

    second_net = RiverNetwork()
    second_net.dict_attr_fields['id'] = RID_B

    second_net.load_data(routes_B, links_B)


    frompoints_OID = arcpy.Describe(frompoints).OIDFieldName
    search = arcpy.da.SearchCursor(frompoints, [frompoints_OID, second_net.dict_attr_fields["id"]])
    dict_fpid_secondid = {}
    for row in search:
        dict_fpid_secondid[row[0]] = row[1]

    # initiate dict_match
    dict_match = {}
    for reach in refD8_net.browse_reaches_down_to_up():
        dict_match[reach.id] = []
    topologicaldif_warning = False

    for reach in refD8_net.get_upstream_ends():

        list_reaches_refD8 = []
        current_reach = reach
        while current_reach is not None:
            list_reaches_refD8.append(current_reach.id)
            current_reach = current_reach.get_downstream_reach()
        list_reaches_second = []
        current_reach = second_net.get_reach(dict_fpid_secondid[reach.ORIG_FID])
        while current_reach is not None:
            list_reaches_second.append(current_reach.id)
            current_reach = current_reach.get_downstream_reach()
        if len(list_reaches_refD8) == len(list_reaches_second):
            # Both paths are going through the same number of reaches
            for i in range(0, len(list_reaches_refD8)):
                dict_match[list_reaches_refD8[i]].append(list_reaches_second[i])
        else:
            topologicaldif_warning = True
            if final_selection == "BEST_FIT":
                # Every combination of potential matching paths are added to the dict_match
                diflen = len(list_reaches_refD8) - len(list_reaches_second)
                if diflen > 0:
                    for shift in range(0, diflen+1):
                        for i in range(0, len(list_reaches_second)):
                            dict_match[list_reaches_refD8[i+shift]].append(list_reaches_second[i])
                else:
                    for shift in range(0, abs(diflen) + 1):
                        for i in range(0, len(list_reaches_refD8)):
                            dict_match[list_reaches_refD8[i]].append(list_reaches_second[i+shift])
            else: #final_selection = "ENDS"
                # Only the combinations with a match upstream are added
                diflen = len(list_reaches_refD8) - len(list_reaches_second)
                if diflen > 0:
                    for i in range(0, len(list_reaches_second)):
                        dict_match[list_reaches_refD8[i]].append(list_reaches_second[i])
                else:
                    for i in range(0, len(list_reaches_refD8)):
                        dict_match[list_reaches_refD8[i]].append(list_reaches_second[i])

    if topologicaldif_warning:
        messages.addWarningMessage("Topological difference between networks detected. Check results.")

    # Geometric comparison: looking for the closest reach based on centroid
    d8centroid = gc.CreateScratchName("pts_D8", data_type="FeatureClass", workspace="in_memory")
    arcpy.FeatureToPoint_management(refD8_net.shapefile, d8centroid)
    secondcentroid = gc.CreateScratchName("pts_second", data_type="FeatureClass", workspace="in_memory")
    arcpy.FeatureToPoint_management(second_net.shapefile, secondcentroid)
    neartable = gc.CreateScratchName("neartable", data_type="ArcInfoTable", workspace="in_memory")
    arcpy.GenerateNearTable_analysis(d8centroid, secondcentroid, neartable)

    arcpy.JoinField_management(neartable, "IN_FID", d8centroid, arcpy.Describe(d8centroid).OIDFieldName, refD8_net.dict_attr_fields["id"])
    arcpy.JoinField_management(neartable, "NEAR_FID", secondcentroid,
                               arcpy.Describe(secondcentroid).OIDFieldName, second_net.dict_attr_fields["id"])
    # in case the two RID have the same name, the result of the join can be a field with a different name
    # let just take the two last field instead of their original name
    two_last_fields = [f.name for f in arcpy.ListFields(neartable)][-2:]
    geometry_match = {}
    search = arcpy.da.SearchCursor(neartable, two_last_fields)
    for row in search:
        geometry_match[row[0]] = row[1]

    # Compilation of the results
    # From each list in the dict_match (i.e. for each reach in refD8), we have a list of possible id in the second net
    # We take the id that has the majority of occurences in the list, and compute its percentage of occurence
    # When there is a tie, so closest geometric match is taken
    # Finally, a warning is set of the result is not the closest geometric match
    arcpy.CreateTable_management(os.path.dirname(matching_table), os.path.basename(matching_table))
    arcpy.AddField_management(matching_table, refD8_net.dict_attr_fields["id"], "LONG")
    arcpy.AddField_management(matching_table, "MATCH_ID", "LONG")
    arcpy.AddField_management(matching_table, "TYPO", "FLOAT")
    arcpy.AddField_management(matching_table, "CLOSEST", "SHORT")
    arcpy.AddField_management(matching_table, "SCORE", "FLOAT")
    insert = arcpy.da.InsertCursor(matching_table, [refD8_net.dict_attr_fields["id"], "MATCH_ID", "TYPO", "CLOSEST", "SCORE"])
    for reach in refD8_net.browse_reaches_down_to_up():
        # the following instruction returns a list of tuples (id, number_of_occurences), ordered by number_of_occurences
        counter = Counter(dict_match[reach.id]).most_common()
        matching_id, occurences = counter[0]
        if len(counter)>1:
            matching_id2, occurences2 = counter[1]
            if occurences == occurences2 and matching_id2==geometry_match[reach.id]:
                # Tie with the second one matching the geometric match
                matching_id = matching_id2
        perc_occurences = occurences/len(dict_match[reach.id])
        geomatch = matching_id==geometry_match[reach.id]
        # Hardcoded weights for the final score. Can be changed.
        score = perc_occurences*0.6+geomatch*0.4
        insert.insertRow([reach.id, matching_id, perc_occurences, geomatch, score])

def execute_LocateMostDownstreamPoints(network_shp, links_table, RID_field, datapoints, id_field_pts, RID_field_pts, Distance_field_pts, X_field_pts, Y_field_pts, output_pts):

    network = RiverNetwork()
    network.dict_attr_fields['id'] = RID_field
    network.load_data(network_shp, links_table)

    collection = Points_collection(network, "data")
    collection.dict_attr_fields['id'] = id_field_pts
    collection.dict_attr_fields['reach_id'] = RID_field_pts
    collection.dict_attr_fields['dist'] = Distance_field_pts
    collection.dict_attr_fields['X'] = X_field_pts
    collection.dict_attr_fields['Y'] = Y_field_pts
    collection.load_table(datapoints)

    arcpy.CreateFeatureclass_management(os.path.dirname(output_pts), os.path.basename(output_pts), "POINT", spatial_reference=network.SpatialReference)
    arcpy.AddField_management(output_pts, collection.dict_attr_fields["id"], "LONG")
    insert = arcpy.da.InsertCursor(output_pts, ["SHAPE@XY", collection.dict_attr_fields["id"]])

    for reach in network.browse_reaches_down_to_up():
        point = reach.get_first_point(collection)
        shape = arcpy.Point(point.X, point.Y)
        insert.insertRow([shape, point.id])
    del insert

def execute_PlacePointsAlongReaches(network_shp, links_table, RID_field, interval, output_pt):

    network = RiverNetwork()
    network.dict_attr_fields['id'] = RID_field
    network.load_data(network_shp, links_table)

    newpoints = Points_collection(network, "newpts")

    network.placePointsAtRegularInterval(interval, newpoints)

    newpoints.save_points(output_pt)

def execute_OrderTreeByFlowAcc(network_shp, links_table, RID_field, datapoints, id_field_pts, RID_field_pts, Distance_field_pts, flow_acc_field, output_field = "order"):
    network = RiverNetwork()
    network.dict_attr_fields['id'] = RID_field
    network.load_data(network_shp, links_table)

    collection = Points_collection(network, "data")
    collection.dict_attr_fields['id'] = id_field_pts
    collection.dict_attr_fields['reach_id'] = RID_field_pts
    collection.dict_attr_fields['dist'] = Distance_field_pts
    collection.dict_attr_fields['discharge'] = flow_acc_field

    collection.load_table(datapoints)

    network.order_reaches_by_discharge(collection, "discharge")

    # Save
    arcpy.AddField_management(network_shp, output_field, "LONG")
    cursor = arcpy.da.UpdateCursor(network_shp, [RID_field, output_field])
    for reach in cursor:
        reach[1] = network.get_reach(reach[0]).order
        cursor.updateRow(reach)
















