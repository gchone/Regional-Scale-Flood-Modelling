# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Concordia University
# Geography, Planning and Environment Department
# guenole.chone@concordia.ca
# Mars 2017
#####################################################

# v1.4 - Octobre 2019 - Input des débits à la limite de la tuile (v1.1, v1.2, v1.3) abandonné.
#       Retour à la v1.0 + Ajout du débit manquant lors d'une confluence + Valeurs par défaut + Ajout Minslope (au lieu de max) + Suppression param lacs
# v1.5 - Octobre 2019 - version modifiée pour simulations de l'amont vers l,aval avec reprise de l'élévation aval comme condition limite:
# v1.6 - Octobre 2019 - Débits ajustés jusqu'à la fin de la zone
# v1.7 - Mai 2020 - Séparation de l'interface - Adaption à CreateZones v1.6 - Fusion avec PrepaSim
# v1.8 - Aoput 2020 - Débogage fenêtre de sortie

import os

from RasterIO import *


class pointflowpath:
   pass


def execute_DefBCI(r_flowdir, r_flowacc, distoutput, percent, str_zonesfolder,
                   r_dem, r_width, r_zbed, r_manning, r_mask, str_outputfolder, messages):


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
        messages.addErrorMessage(e.message)

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




    ### Début de traitement pour la configuration des fenêtres de sortie ###

    # Pour chaque point de sortie
    for point in listoutputpoints:
        raster = RasterIO(arcpy.Raster(str_zonesfolder + r"\zone" + str(point.numzone)))
        colinc = 0
        rowinc = 0
        distinc = 0
        point.side2 = "0"
        point.lim3 = 0
        point.lim4 = 0
        # Selon le coté de sortie, on progressera horizontalement ou verticalement
        if point.side == "W" or point.side == "E":
            rowinc = 1
            distinc = raster.raster.meanCellHeight
        else:
            colinc = 1
            distinc = raster.raster.meanCellWidth
        currentcol = raster.XtoCol(point.X)
        currentrow = raster.YtoRow(point.Y)
        distance = 0
        # On progresse sur dans une direction jusqu'à sortir du raster ou jusqu'à ce que la distance voullue soit attente
        while (not (currentcol < 0 or currentcol >= raster.raster.width or currentrow < 0 or currentrow >= raster.raster.height)) \
                and raster.getValue(currentrow,currentcol) != raster.nodata and distance < distoutput/2:
            distance += distinc
            currentrow += rowinc
            currentcol += colinc
        # On prends les coordonnées avant de sortir du raster
        currentrow -= rowinc
        currentcol -= colinc
        if point.side == "W" or point.side == "E":
            point.lim1 = raster.RowtoY(currentrow)
        else:
            point.lim1 = raster.ColtoX(currentcol)
        # Si la procédure s'est arrêtée parce qu'on est sorti du raster, on tourne de 90 degrés et on continue
        if distance < distoutput / 2:
            distance -= distinc
            if point.side == "W":
                colinc = 1
                rowinc = 0
                distinc = raster.raster.meanCellWidth
                point.lim3 = raster.raster.extent.XMin + (currentcol + 0.5) * raster.raster.meanCellWidth
            elif point.side == "E":
                colinc = -1
                rowinc = 0
                distinc = raster.raster.meanCellWidth
                point.lim3 = raster.raster.extent.XMin + (currentcol + 0.5) * raster.raster.meanCellWidth

            elif point.side == "N":
                rowinc = 1
                colinc = 0
                distinc = raster.raster.meanCellHeight
                point.lim3 = max(raster.raster.extent.YMin, raster.raster.extent.YMax - (currentrow + 1) * raster.raster.meanCellHeight) + 0.5 * raster.raster.meanCellHeight
            elif point.side == "S":
                rowinc = -1
                colinc = 0
                distinc = raster.raster.meanCellHeight
                point.lim3 = max(raster.raster.extent.YMin, raster.raster.extent.YMax - (currentrow + 1) * raster.raster.meanCellHeight) + 0.5 * raster.raster.meanCellHeight
            # On progresse à nouveau jusqu'à sortir du raster ou jusqu'à ce que la distance voullue soit attente
            while (not (currentcol < 0 or currentcol >= raster.raster.width or currentrow < 0 or currentrow >= raster.raster.height)) \
                    and raster.getValue(currentrow, currentcol) != raster.nodata and distance < distoutput / 2:
                distance += distinc
                currentrow += rowinc
                currentcol += colinc
            currentrow -= rowinc
            currentcol -= colinc
            # On cherche sur quel coté on est après avoir tourné de 90 degrés
            if point.side == "W" or point.side == "E":
                point.side2 = "S"
                point.lim4 = raster.raster.extent.XMin + (currentcol + 0.5) * raster.raster.meanCellWidth
            else:
                point.side2 = "E"
                point.lim4 = max(raster.raster.extent.YMin, raster.raster.extent.YMax - (currentrow + 1) * raster.raster.meanCellHeight) + 0.5 * raster.raster.meanCellHeight

        # On recommence toute la procédure de l'autre côté du point de sortie
        colinc = 0
        rowinc = 0
        distinc = 0
        if point.side == "W" or point.side == "E":
            rowinc = -1
            distinc = raster.raster.meanCellHeight
        else:
            colinc = -1
            distinc = raster.raster.meanCellWidth
        currentcol = raster.XtoCol(point.X)
        currentrow = raster.YtoRow(point.Y)
        distance = 0
        while (not (currentcol < 0 or currentcol >= raster.raster.width or currentrow < 0 or currentrow >= raster.raster.height)) \
                and raster.getValue(currentrow, currentcol) != raster.nodata and distance < distoutput / 2:
            distance += distinc
            currentrow += rowinc
            currentcol += colinc
        currentrow -= rowinc
        currentcol -= colinc
        if point.side == "W" or point.side == "E":
            point.lim2 = max(raster.raster.extent.YMin, raster.raster.extent.YMax - (currentrow + 1) * raster.raster.meanCellHeight) + 0.5 * raster.raster.meanCellHeight
        else:
            point.lim2 = raster.raster.extent.XMin + (currentcol + 0.5) * raster.raster.meanCellWidth
        # Si la procédure s'est arrêtée parce qu'on est sorti du raster, on tourne de 90 degrés et on continue
        if distance < distoutput / 2:
            distance -= distinc
            if point.side == "W":
                colinc = 1
                rowinc = 0
                distinc = raster.raster.meanCellWidth
                point.lim3 = raster.raster.extent.XMin + (currentcol + 0.5) * raster.raster.meanCellWidth
            elif point.side == "E":
                colinc = -1
                rowinc = 0
                distinc = raster.raster.meanCellWidth
                point.lim3 = raster.raster.extent.XMin + (currentcol + 0.5) * raster.raster.meanCellWidth
            elif point.side == "N":
                rowinc = 1
                colinc = 0
                distinc = raster.raster.meanCellHeight
                point.lim3 = max(raster.raster.extent.YMin, raster.raster.extent.YMax - (currentrow + 1) * raster.raster.meanCellHeight) + 0.5 * raster.raster.meanCellHeight
            elif point.side == "S":
                rowinc = -1
                colinc = 0
                distinc = raster.raster.meanCellHeight
                point.lim3 = max(raster.raster.extent.YMin, raster.raster.extent.YMax - (currentrow + 1) * raster.raster.meanCellHeight) + 0.5 * raster.raster.meanCellHeight
            while (not (currentcol < 0 or currentcol >= raster.raster.width or currentrow < 0 or currentrow >= raster.raster.height)) \
                and raster.getValue(currentrow, currentcol) != raster.nodata and distance < distoutput / 2:
                distance += distinc
                currentrow += rowinc
                currentcol += colinc
            currentrow -= rowinc
            currentcol -= colinc
            if point.side == "W" or point.side == "E":
                point.side2 = "N"
                point.lim4 = raster.raster.extent.XMin + (currentcol + 0.5) * raster.raster.meanCellWidth
            else:
                point.side2 = "W"
                point.lim4 = max(raster.raster.extent.YMin, raster.raster.extent.YMax - (currentrow + 1) * raster.raster.meanCellHeight) + 0.5 * raster.raster.meanCellHeight

    ### Fin du traitement pour la configuration des fenêtres de sortie ###


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
    arcpy.AddField_management(save_outbci, "lim1", "LONG")
    arcpy.AddField_management(save_outbci, "lim2", "LONG")
    arcpy.AddField_management(save_outbci, "side2", "TEXT", field_length=1, )
    arcpy.AddField_management(save_outbci, "lim3", "LONG")
    arcpy.AddField_management(save_outbci, "lim4", "LONG")


    # Enregistrement dans les shapefiles des informations contenues dans les listes
    pointcursor = arcpy.da.InsertCursor(save_inbci, ["zoneid", "flowacc", "type", "fpid", "SHAPE@XY"])
    for point in listinputpoints:
        pointcursor.insertRow([point.numzone, point.flowacc, point.type, point.frompointid, (point.X, point.Y)])
    pointcursor = arcpy.da.InsertCursor(save_outbci, ["zoneid", "side", "lim1", "lim2", "side2", "lim3", "lim4", "SHAPE@XY"])
    for point in listoutputpoints:
        pointcursor.insertRow([point.numzone, point.side, point.lim1, point.lim2, point.side2, point.lim3, point.lim4,(point.X, point.Y)])

    del pointcursor



    # Création des fichiers .bci à partir des information du fichier inbci.shp

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

    # Ajout de la zone de sortie au .bci
    bcipointcursor = arcpy.da.SearchCursor(save_outbci,
                                           ["zoneid", "side", "lim1", "lim2", "side2", "lim3", "lim4", "SHAPE@"])
    for point in bcipointcursor:
        newfile = str_outputfolder + "\\zone" + str(point[0]) + ".bci"
        filebci = open(newfile, 'a')
        filebci.write(point[1] + "\t" + str(point[2]) + "\t" + str(point[3]) + "\tHVAR\thvar")
        if str(point[4]) != "0":
            filebci.write("\n" + str(point[4]) + "\t" + str(point[5]) + "\t" + str(point[6]) + "\tHVAR\thvar")
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

    return