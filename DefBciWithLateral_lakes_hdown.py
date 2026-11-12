# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Concordia University
# Geography, Planning and Environment Department
# guenole.chone@concordia.ca
#####################################################


import os
import uuid

from RasterIO import *


class pointflowpath:
   pass


def execute_DefBCI(r_flowdir, r_flowacc, percent, str_zonesfolder,
                   r_dem, r_width, r_zbed, r_manning, r_mask, str_outputfolder, messages,
                   river_network):

    if not os.path.isdir(str_outputfolder):
        os.makedirs(str_outputfolder)

    save_inbci = str_zonesfolder + "\\inbci.shp"
    save_outbci = str_zonesfolder + "\\outbci.shp"

    # Chargement des fichiers
    flowdir = RasterIO(r_flowdir)
    flowacc = RasterIO(r_flowacc)
    dem = RasterIO(r_dem)



    try:
        flowdir.checkMatch(flowacc)
        flowdir.checkMatch(dem)
    except Exception as e:
        messages.addErrorMessage(repr(e))

    # Création d'un nouveau fichier de zones en prenant les enveloppes
    zones = str_zonesfolder + "\\envelopezones.shp"
    arcpy.FeatureEnvelopeToPolygon_management( str_zonesfolder + "\\polyzones.shp", zones)

    # Clip du DEM

    zonesscursor = arcpy.da.SearchCursor(zones, ["GRID_CODE", "SHAPE@"])
    for zoneshp in zonesscursor:

        Xmin = zoneshp[1].extent.XMin
        Ymin = zoneshp[1].extent.YMin
        Xmax = zoneshp[1].extent.XMax
        Ymax = zoneshp[1].extent.YMax
        envelope = str(Xmin) + " " + str(Ymin) + " " + str(Xmax) + " " + str(Ymax)
        arcpy.Clip_management(dem.raster, envelope, str_zonesfolder + "\\zone" + str(zoneshp[0]))

    # Listes des points source et des points de sortie
    listinputpoints = []
    listoutputpoints = []


    # Lectures des points source pour chaque zone
    sourcepointcursor = arcpy.da.SearchCursor(str_zonesfolder + "\\sourcepoints.shp", ["SHAPE@", "ZoneID", "fpid"])
    for sourcepoint in sourcepointcursor:
        newpoint = pointflowpath()
        newpoint.type = "main"
        newpoint.frompointid = sourcepoint[2]
        # Coordonnées du point source
        newpoint.X = sourcepoint[0].firstPoint.X
        newpoint.Y = sourcepoint[0].firstPoint.Y
        # Raster de la zone
        newpoint.numzone = sourcepoint[1]
        # Valeur du flow accumulation
        col = flowacc.XtoCol(newpoint.X)
        row = flowacc.YtoRow(newpoint.Y)
        newpoint.flowacc = flowacc.getValue(row, col)

        listinputpoints.append(newpoint)


    ### Début de traitement pour la détection des points de sortie et des points sources latéraux ###


    listlateralinputpoints = []

    # Pour chaque raster, on parcourt l'écoulement à partir du point source
    for mainpoint in listinputpoints:

        # Raster de la zone correspondante au point source
        localraster = RasterIO(arcpy.Raster(str_zonesfolder + r"\zone" + str(mainpoint.numzone)))

        # Conversion des coordonnées
        currentcol = flowdir.XtoCol(mainpoint.X)
        currentrow = flowdir.YtoRow(mainpoint.Y)
        localcol = localraster.XtoCol(mainpoint.X)
        localrow = localraster.YtoRow(mainpoint.Y)

        currentflowacc = flowacc.getValue(currentrow, currentcol)
        mainpoint.flowacc = currentflowacc
        lastflowacc = currentflowacc

        # Parcours de l'écoulement
        intheraster = True
        while (intheraster):

            prevcol = currentcol
            prevrow = currentrow

            currentflowacc = flowacc.getValue(currentrow, currentcol)

            if currentflowacc == 0:
                raise Exception("Flow accumulation value of zero uncountered. Check that source points are located on the flow network.")

            if 100. * float(currentflowacc - lastflowacc) / float(
                    lastflowacc) >= percent:
                newpoint = pointflowpath()
                newpoint.type = "lateral"
                newpoint.frompointid = mainpoint.frompointid
                # Coordonnées du point source
                newpoint.X = flowdir.ColtoX(currentcol)
                newpoint.Y = flowdir.RowtoY(currentrow)
                # Raster de la zone
                newpoint.numzone = mainpoint.numzone
                # Valeur du flow accumulation
                newpoint.flowacc = currentflowacc
                lastflowacc = currentflowacc

                listlateralinputpoints.append(newpoint)

            # On cherche le prochain point à partir du flow direction
            direction = flowdir.getValue(currentrow, currentcol)
            if (direction == 1):
                currentcol = currentcol + 1
                localcol += 1
            if (direction == 2):
                currentcol = currentcol + 1
                currentrow = currentrow + 1
                localcol += 1
                localrow += 1

            if (direction == 4):
                currentrow = currentrow + 1
                localrow += 1

            if (direction == 8):
                currentcol = currentcol - 1
                currentrow = currentrow + 1
                localcol -= 1
                localrow += 1

            if (direction == 16):
                currentcol = currentcol - 1
                localcol -= 1

            if (direction == 32):
                currentcol = currentcol - 1
                currentrow = currentrow - 1
                localcol -= 1
                localrow -= 1

            if (direction == 64):
                currentrow = currentrow - 1
                localrow -= 1

            if (direction == 128):
                currentcol = currentcol + 1
                currentrow = currentrow - 1
                localcol += 1
                localrow -= 1

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

            if localcol < 0 or localcol >= localraster.raster.width or localrow < 0 or localrow >= localraster.raster.height:
                intheraster = False
            elif localraster.getValue(localrow, localcol) == localraster.nodata:
                intheraster = False


        # On enregistre un point de sortie au dernier point traité avant de sortir de la zone
        newpoint = pointflowpath()
        newpoint.numzone = mainpoint.numzone
        newpoint.X = flowdir.ColtoX(prevcol)
        newpoint.Y = flowdir.RowtoY(prevrow)



        # Il est nécessaire d'enregistrer le côté du raster par lequel on sort.
        # Ceci est fait en regardant la distance entre le dernier point traité et les coordonnées maximales de la zone
        # Le côté de sortie est le côté pour lequel cette distance est minimum
        distside = min(newpoint.X - localraster.raster.extent.XMin, localraster.raster.extent.XMax - newpoint.X,
                       newpoint.Y - localraster.raster.extent.YMin,
                       localraster.raster.extent.YMax - newpoint.Y)
        if distside == newpoint.X - localraster.raster.extent.XMin:
            newpoint.side = "W"
        if distside == localraster.raster.extent.XMax - newpoint.X:
            newpoint.side = "E"
        if distside == newpoint.Y - localraster.raster.extent.YMin:
            newpoint.side = "S"
        if distside == localraster.raster.extent.YMax - newpoint.Y:
            newpoint.side = "N"
        listoutputpoints.append(newpoint)

    listinputpoints.extend(listlateralinputpoints)
    ### Fin de traitement pour la détection des points de sortie et des points sources latéraux ###





    # Création des shapefiles inbci et outbci, avec les champs nécessaires
    arcpy.CreateFeatureclass_management(os.path.dirname(save_inbci),
                                        os.path.basename(save_inbci), "POINT", spatial_reference = flowdir.raster.spatialReference)
    arcpy.AddField_management(save_inbci, "zoneid", "LONG")
    arcpy.AddField_management(save_inbci, "flowacc", "LONG")
    arcpy.AddField_management(save_inbci, "type", "TEXT")
    arcpy.AddField_management(save_inbci, "fpid", "LONG")
    arcpy.CreateFeatureclass_management(os.path.dirname(save_outbci),
                                        os.path.basename(save_outbci), "POINT", spatial_reference=flowdir.raster.spatialReference)
    arcpy.AddField_management(save_outbci, "zoneid", "LONG")
    arcpy.AddField_management(save_outbci, "side", "TEXT", field_length=1)


    # Enregistrement dans les shapefiles des informations contenues dans les listes
    pointcursor = arcpy.da.InsertCursor(save_inbci, ["zoneid", "flowacc", "type", "fpid", "SHAPE@XY"])
    for point in listinputpoints:
        pointcursor.insertRow([point.numzone, point.flowacc, point.type, point.frompointid, (point.X, point.Y)])
    pointcursor = arcpy.da.InsertCursor(save_outbci, ["zoneid", "side", "SHAPE@XY"])
    for point in listoutputpoints:
        pointcursor.insertRow([point.numzone, point.side, (point.X, point.Y)])

    del pointcursor



    # Création des fichiers .bci à partir des informations du fichier inbci.shp

    bcipointcursor = arcpy.da.SearchCursor(save_inbci, ["SHAPE@", "zoneid", "flowacc", "type"])
    dictsegmentsin = {}
    for point in bcipointcursor:
        if point[1] not in dictsegmentsin:
            dictsegmentsin[point[1]] = []
        dictsegmentsin[point[1]].append(point)

    for segment in dictsegmentsin.values():
        for point in sorted(segment, key=lambda q: q[2]):
            if point[3] == "main":
                latnum = 0

                pointshape = point[0].firstPoint



                # Création du fichier
                newfile = str_outputfolder + "\\zone" + str(point[1]) + ".bci"

                # Enregistrement des coordonnées pour le point source
                filebci = open(newfile, 'w')
                filebci.write(
                    "P\t" + str(int(pointshape.X)) + "\t" + str(int(pointshape.Y)) + "\tQVAR\tzone" + str(point[1]) + "\n")
                filebci.close()


            if point[3] == "lateral":
                pointshape = point[0].firstPoint

                latnum += 1
                newfile = str_outputfolder + "\\zone" + str(point[1]) + ".bci"

                # Enregistrement des coordonnées et du débit pour le point source
                filebci = open(newfile, 'a')
                filebci.write(
                    "P\t" + str(int(pointshape.X)) + "\t" + str(int(pointshape.Y)) + "\tQVAR\tzone" + str(point[1]) + "_" + str(
                        latnum) + "\n")
                filebci.close()



    # Création des fichiers .par et conversion des rasters en fichiers ASCII (un par point source comme il n'y a qu'un seul point d'entrée par simulation)

    for segment in dictsegmentsin.values():
        for point in sorted(segment, key=lambda q: q[2]):

            if point[3] == "main":


                arcpy.Clip_management(r_width, "#", str_zonesfolder + r"\wzone" + str(point[1]), str_zonesfolder + "\\zone" + str(point[1]),
                                      "#", "NONE", "MAINTAIN_EXTENT")
                arcpy.Clip_management(r_zbed, "#", str_zonesfolder + r"\dzone" + str(point[1]), str_zonesfolder + "\\zone" + str(point[1]),
                                      "#", "NONE", "MAINTAIN_EXTENT")
                arcpy.Clip_management(r_manning, "#", str_zonesfolder + r"\nzone" + str(point[1]), str_zonesfolder + "\\zone" +str(point[1]),
                                      "#", "NONE", "MAINTAIN_EXTENT")


                arcpy.RasterToASCII_conversion(str_zonesfolder + "\\zone" + str(point[1]),
                                               str_outputfolder + "\\zone" + str(point[1]) + ".txt")
                arcpy.RasterToASCII_conversion(str_zonesfolder + "\dzone" + str(point[1]),
                                               str_outputfolder + "\\dzone" + str(point[1]) + ".txt")
                arcpy.RasterToASCII_conversion(str_zonesfolder + "\wzone" + str(point[1]),
                                               str_outputfolder + "\\wzone" + str(point[1]) + ".txt")

                arcpy.RasterToASCII_conversion(str_zonesfolder + "\\nzone" + str(point[1]),
                                               str_outputfolder + "\\nzone" + str(point[1]) + ".txt")
                arcpy.Delete_management(str_zonesfolder + r"\wzone" + str(point[1]))
                arcpy.Delete_management(str_zonesfolder + r"\dzone" + str(point[1]))
                arcpy.Delete_management(str_zonesfolder + r"\nzone" + str(point[1]))



                arcpy.Clip_management(r_mask, "#", str_zonesfolder + r"\mzone" + str(point[1]),
                                      str_zonesfolder + "\\zone" + str(point[1]),
                                      "#", "NONE", "MAINTAIN_EXTENT")
                arcpy.RasterToASCII_conversion(str_zonesfolder + "\mzone" + str(point[1]),
                                               str_outputfolder + "\\mzone" + str(point[1]) + ".txt")
                arcpy.Delete_management(str_zonesfolder + r"\mzone" + str(point[1]))

    buffer_distance = max(abs(flowdir.raster.meanCellWidth), abs(flowdir.raster.meanCellHeight))
    create_maxoutput(zones, save_outbci, river_network,
                     os.path.join(str_zonesfolder, "maxoutput.shp"), buffer_distance)

    return


def create_maxoutput(zones, outlets, river_network, output, buffer_distance=0):
    """Create the outlet's border-point Thiessen polygon for each zone, enlarged by buffer_distance."""
    scratch = arcpy.env.scratchGDB
    zone_lines = arcpy.CreateUniqueName("zone_lines", scratch)
    intersections = arcpy.CreateUniqueName("border_intersections", scratch)
    points = arcpy.CreateUniqueName("border_points", scratch)
    thiessen = arcpy.CreateUniqueName("border_thiessen", scratch)
    result = arcpy.CreateUniqueName("maxoutput", scratch)
    line_layer = "zone_line_" + uuid.uuid4().hex
    temporary = [line_layer, thiessen, points, intersections, zone_lines, result]
    spatial_reference = arcpy.Describe(zones).spatialReference

    try:
        outlet_by_zone = {}
        with arcpy.da.SearchCursor(outlets, ["zoneid", "SHAPE@"]) as cursor:
            for zone_id, geometry in cursor:
                if zone_id in outlet_by_zone:
                    raise ValueError("Multiple output boundary points for zone {}.".format(zone_id))
                outlet_by_zone[zone_id] = geometry

        with arcpy.EnvManager(extent=None, outputCoordinateSystem=spatial_reference):
            arcpy.PolygonToLine_management(zones, zone_lines, "IGNORE_NEIGHBORS")
            arcpy.MakeFeatureLayer_management(zone_lines, line_layer)
            arcpy.CreateFeatureclass_management(
                scratch, os.path.basename(result), "POLYGON",
                spatial_reference=spatial_reference)
            arcpy.AddField_management(result, "zoneid", "LONG")

            seen_zones = set()
            with arcpy.da.SearchCursor(zones, ["OID@", "GRID_CODE", "SHAPE@"]) as zone_cursor:
                with arcpy.da.InsertCursor(result, ["zoneid", "SHAPE@"]) as result_cursor:
                    for oid, zone_id, zone_geometry in zone_cursor:
                        if zone_id in seen_zones:
                            raise ValueError("Multiple envelope features for zone {}.".format(zone_id))
                        seen_zones.add(zone_id)
                        if zone_id not in outlet_by_zone:
                            raise ValueError("No output boundary point for zone {}.".format(zone_id))

                        where = "{} = {}".format(arcpy.AddFieldDelimiters(zone_lines, "ORIG_FID"), oid)
                        arcpy.SelectLayerByAttribute_management(line_layer, "NEW_SELECTION", where)
                        arcpy.analysis.PairwiseIntersect(
                            [line_layer, river_network], intersections, "ONLY_FID", output_type="POINT")
                        arcpy.MultipartToSinglepart_management(intersections, points)
                        arcpy.DeleteIdentical_management(points, ["Shape"])
                        if int(arcpy.GetCount_management(points)[0]) == 0:
                            raise ValueError("No river network intersections on the border of zone {}.".format(zone_id))

                        with arcpy.EnvManager(extent=zone_geometry.extent):
                            arcpy.analysis.CreateThiessenPolygons(points, thiessen)

                        candidates = []
                        with arcpy.da.SearchCursor(thiessen, ["SHAPE@"]) as polygon_cursor:
                            for (polygon,) in polygon_cursor:
                                candidates.append(
                                    (polygon.distanceTo(outlet_by_zone[zone_id]), polygon))
                        if not candidates:
                            raise ValueError("No Thiessen polygon created for zone {}.".format(zone_id))
                        min_distance = min(distance for distance, _ in candidates)
                        matches = [polygon for distance, polygon in candidates
                                   if distance - min_distance <= 1e-9]
                        if len(matches) != 1:
                            raise ValueError(
                                "Expected one Thiessen polygon closest to the output point for zone {}; found {}."
                                .format(zone_id, len(matches)))
                        clipped = matches[0].intersect(zone_geometry, 4)
                        if not clipped or clipped.area == 0:
                            raise ValueError("Empty output polygon for zone {}.".format(zone_id))
                        if buffer_distance:
                            clipped = clipped.buffer(buffer_distance)
                        result_cursor.insertRow([zone_id, clipped])
                        arcpy.Delete_management(thiessen)
                        arcpy.Delete_management(points)
                        arcpy.Delete_management(intersections)

            if not seen_zones:
                raise ValueError("No envelope zones were found.")
            arcpy.CopyFeatures_management(result, output)
    finally:
        for dataset in temporary:
            if arcpy.Exists(dataset):
                arcpy.Delete_management(dataset)