# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Concordia University
# Geography, Planning and Environment Department
# guenole.chone@concordia.ca
# Fevrier 2019
#####################################################

# v1.1 - 10 mai 2018 - Correction des problèmes de zones dupliquées aux confluences (due aux segments d'un pixel de
#   long). Correction des longueurs des segments aux confluences.
# v1.2 - 28 février 2019 - Suppression des coupures aux confluences, ajout des coupures aux lacs.
# v1.3 - septembre 2019 - Coupure nette des rasters aux lacs + ajout du critère de pente
# v1.4 - octobre 2019 - Debug : problème de coupure des lacs avec multi fp, problème si zone de lac trop courte
# v1.5 - fevrier 2020 - Debug : problème de clip pour les confluent des segments coupé par les lacs
# v1.6 - mai 2020 - Coupure pour SUB et SUPER GC - Séparation interface et metier - Suppression de l'utilisation de la hauteur des lacs
#    - suppression de l'utilisation du DEM et ouput sous forme de shapefiles (sourcepoints.shp et polyzones.shp)
# v1.7 - juillet 2020 - Coupure pour SUB et SUPER GC supprimé: distinction faite par le masque
# v1.8 - aout 2020 - pente optionnelle

from RasterIO import *

class pointflowpath:
   pass



def execute_CreateZone(r_flowdir, str_lakes, r_slope, minslope, str_frompoint, distance, bufferw, str_zonesfolder, messages):



    str_segments = str_zonesfolder + "\\segments"
    str_linesegments = str_zonesfolder + "\\line_segments.shp"
    str_bufferedsegments = str_zonesfolder + "\\buff_segments.shp"

    save_sourcepoints = str_zonesfolder + "\\sourcepoints.shp"

    str_r_lakes = str_zonesfolder + "\\r_lakes"

    flowdir = RasterIO(r_flowdir)
    if r_slope is not None:
        slope = RasterIO(r_slope)
        try:
            flowdir.checkMatch(slope)

        except Exception as e:
            messages.addErrorMessage(e.message)
    else:
        slope = None



    # Conversion des lacs en raster et copie
    arcpy.env.snapRaster = flowdir.raster
    arcpy.env.outputCoordinateSystem = flowdir.raster.spatialReference
    arcpy.env.extent = flowdir.raster
    arcpy.PolygonToRaster_conversion(str_lakes, arcpy.Describe(str_lakes).OIDFieldName, str_r_lakes, cellsize = flowdir.raster)
    lakes = RasterIO(arcpy.Raster(str_r_lakes))
    arcpy.CopyFeatures_management(str_lakes, str_zonesfolder + "\\lakes.shp")
    str_lakes = str_zonesfolder + "\\lakes.shp"
    arcpy.AddGeometryAttributes_management(str_lakes, "EXTENT")

    ### Début du traitement perrmettant d'identifier les segments (sous forme de raster) ###

    raster_segments = RasterIO(r_flowdir, str_segments, int,-255)

    # numérotation des segments
    segnumber = 0

    lakes_bci = {}
    toclip = {}
    inputpoints = {}

    # Pour chaque point de départ
    frompointcursor = arcpy.da.SearchCursor(str_frompoint, ["SHAPE@", "OID@"])
    for frompoint in frompointcursor:

        # On prend l'objet géométrique (le point) associé à la ligne dans la table
        frompointshape = frompoint[0].firstPoint

        # Nouvelle rivière : on change de segment
        segnumber += 1

        # Conversion des coordonnées
        currentcol = flowdir.XtoCol(frompointshape.X)
        currentrow = flowdir.YtoRow(frompointshape.Y)



        # Tests de sécurité pour s'assurer que le point de départ est à l'intérieurs des rasters
        intheraster = True
        if currentcol<0 or currentcol>=flowdir.raster.width or currentrow<0 or currentrow>= flowdir.raster.height:
            intheraster = False
        elif (flowdir.getValue(currentrow, currentcol) != 1 and flowdir.getValue(currentrow, currentcol) != 2 and
                            flowdir.getValue(currentrow, currentcol) != 4 and flowdir.getValue(currentrow, currentcol) != 8 and
                            flowdir.getValue(currentrow, currentcol) != 16 and flowdir.getValue(currentrow, currentcol) != 32 and flowdir.getValue(currentrow, currentcol) != 64 and flowdir.getValue(currentrow, currentcol) != 128):
            intheraster = False


        listpointsflowpath = []
        totaldistance = 0
        currentdistance = 0
        inlake = True
        # True si la rivière (depuis le point de départ jusqu'au confluent) est composée d'au moins deux segments
        dividedriver = False
        # listtomerged contient la liste des segments trop courts, qui doivent être fusionnés avec segment précédent
        listtomerged = []


        # Pour chaque cellule en suivant l'écoulement
        while (intheraster):


            waslake = inlake

            inlake = False
            lakevalue = lakes.getValue(currentrow, currentcol)

            inlake = (lakevalue != lakes.nodata)


            if not (inlake and waslake):
                # Distance parcourue depuis le début du segment
                totaldistance = totaldistance + currentdistance


            slope_criteria = True
            if slope is not None:
                slope_criteria = slope.getValue(currentrow,currentcol) > minslope

            # Test si on arrive à un lac
            if inlake and not waslake:
                # Segment trop court si de longueur inférieure à 30% de la distance voullue
                # Le segment doit être alors fusionné avec le segment précédent (qui existe uniquement si dividedriver = True)
                # ajout de l'info de clipper ensuite également
                coordX = flowdir.ColtoX(currentcol)
                coordY = flowdir.RowtoY(currentrow)

                fieldidlakes = arcpy.Describe(str_lakes).OIDFieldName
                shplakes = arcpy.da.SearchCursor(str_lakes, ["SHAPE@", "EXT_MIN_X", "EXT_MAX_X", "EXT_MIN_Y", "EXT_MAX_Y", fieldidlakes])
                for shplake in shplakes:
                    if shplake[0].contains(arcpy.Point(coordX, coordY)):
                        lakes_bci[segnumber]=shplakes[5]
                        distXmin = abs(coordX - shplake[1])
                        distXmax = abs(coordX - shplake[2])
                        distYmin = abs(coordY - shplake[3])
                        distYmax = abs(coordY - shplake[4])
                        mini = min(distXmin, distXmax, distYmin, distYmax)
                        if mini == distXmin:
                            toclip[segnumber] = ["Xmax", shplake[1]]
                            messages.addMessage(str(segnumber)+" Xmax " + str(shplake[1]))
                        if mini == distXmax:
                            toclip[segnumber] = ["Xmin", shplake[2]]
                            messages.addMessage(str(segnumber) + " Xmin " + str(shplake[2]))
                        if mini == distYmin:
                            toclip[segnumber] = ["Ymax", shplake[3]]
                            messages.addMessage(str(segnumber) + " Ymax " + str(shplake[3]))
                        if mini == distYmax:
                            toclip[segnumber] = ["Ymin", shplake[4]]
                            messages.addMessage(str(segnumber) + " Ymin " + str(shplake[4]))
                if totaldistance < 0.3 * distance and dividedriver:
                    if segnumber in toclip:
                        toclip[segnumber - 1] = toclip.pop(segnumber)
                    listtomerged.append(segnumber)
                totaldistance = 0
                segnumber += 1
                dividedriver = False



            elif totaldistance > distance and slope_criteria:
                # Test si on a parcouru la distance voullue
                totaldistance = 0
                segnumber += 1
                dividedriver = True



            if not inlake:
                # On conseerve une liste des points traités, avec leur numéro de segment
                currentpoint = pointflowpath()
                currentpoint.row = currentrow
                currentpoint.col = currentcol
                currentpoint.X = flowdir.ColtoX(currentcol)
                currentpoint.Y = flowdir.RowtoY(currentrow)
                currentpoint.distance = totaldistance
                currentpoint.segnumber = segnumber
                currentpoint.frompointid = frompoint[1]
                listpointsflowpath.append(currentpoint)

            # On cherche le prochain point à partir du flow direction
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

            # Tests de sécurité pour s'assurer que l'on ne sorte pas des rasters
            if currentcol < 0 or currentcol >= flowdir.raster.width or currentrow < 0 or currentrow >= flowdir.raster.height:
                intheraster = False
            elif (flowdir.getValue(currentrow, currentcol) != 1 and flowdir.getValue(currentrow, currentcol) != 2 and
                            flowdir.getValue(currentrow, currentcol) != 4 and flowdir.getValue(currentrow, currentcol) != 8 and
                            flowdir.getValue(currentrow, currentcol) != 16 and flowdir.getValue(currentrow, currentcol) != 32 and flowdir.getValue(currentrow, currentcol) != 64 and flowdir.getValue(currentrow, currentcol) != 128):
                intheraster = False


            if intheraster:
                confluence_seg = raster_segments.getValue(currentrow, currentcol)
                if (confluence_seg != -255):
                    # Atteinte d'un confluent déjà traité

                    # Si le segment dans lequel on arrive est limité par un lac, le confluent peut l'être aussi
                    # On copie l'item toclip pour limiter l'étendu de la zone
                    # par contre on garde l'élévation à -999 (hfix sera le résultat de la simulation du cours d'eau confluent)
                    if confluence_seg in listtomerged:
                        confluence_seg -= 1
                    if confluence_seg in toclip:
                        clipitem = list(toclip[confluence_seg])
                        toclip[segnumber] = clipitem


                    if totaldistance < 0.3 * distance and dividedriver:
                        # Segment trop court si de longueur inférieure à 30% de la distance voullue
                        # Le segment doit être alors fusionné avec le segment précédent (qui existe uniquement si dividedriver = True)
                        listtomerged.append(segnumber)
                        if segnumber in toclip:
                            toclip[segnumber - 1] = toclip.pop(segnumber)



                    intheraster = False






        # Pour chaque point traité le long de l'écoulement
        for currentpoint in listpointsflowpath:
            # Si c'est un point d'un segment trop court, on remplace le numéro du segment par le numéro du segment précédent
            if currentpoint.segnumber in listtomerged:
                currentpoint.segnumber -= 1
            # On enregistre le point
            raster_segments.setValue(currentpoint.row, currentpoint.col,
                            currentpoint.segnumber)
            if currentpoint.segnumber not in inputpoints:
                newpoint = pointflowpath()
                newpoint.type = "main"
                newpoint.frompointid = currentpoint.frompointid
                # Coordonnées du point source
                newpoint.X = currentpoint.X
                newpoint.Y = currentpoint.Y

                inputpoints[currentpoint.segnumber] = newpoint



    raster_segments.save()

    ### Fin du traitement perrmettant d'identifier les segments ###


    ### Transformation du raster des segments en zones ####

    # Transformation en polyline
    tmp_segments = arcpy.env.scratchWorkspace + "\\tmpsegments.shp"
    arcpy.RasterToPolyline_conversion(str_segments,tmp_segments)
    arcpy.Dissolve_management(tmp_segments,str_linesegments,"GRID_CODE")
    arcpy.Delete_management(tmp_segments)


    # Création de la zone tampon
    # Harcoded : buffer longitudinal de 1/10 de l'extension latérale (obtenue par Euclidienne Allocation)
    tmp_segmentsbuf = arcpy.env.scratchWorkspace + "\\tmpsegments_buf.shp"
    arcpy.Buffer_analysis(str_linesegments, tmp_segmentsbuf, bufferw/10.)
    segalloc = arcpy.sa.EucAllocation(raster_segments.raster, bufferw)
    arcpy.RasterToPolygon_conversion(segalloc, tmp_segments)
    arcpy.AddField_management(tmp_segments, "GRID_CODE", "LONG")
    arcpy.CalculateField_management(tmp_segments, "GRID_CODE",
                                    "!GRIDCODE!", "PYTHON_9.3")
    tmp_segments2 = arcpy.env.scratchWorkspace + "\\tmpsegments2.shp"
    arcpy.Merge_management([tmp_segmentsbuf, tmp_segments], tmp_segments2)
    arcpy.Dissolve_management(tmp_segments2,str_bufferedsegments,["GRID_CODE"], multi_part="SINGLE_PART")

    arcpy.Delete_management(tmp_segments)
    arcpy.Delete_management(tmp_segments2)

    arcpy.Delete_management(str_lakes)

    # Création de la zone pour chaque segment
    arcpy.CreateFeatureclass_management (str_zonesfolder, "polyzones.shp", "POLYGON", str_bufferedsegments, spatial_reference=flowdir.raster.spatialReference)
    polyzones = str_zonesfolder + "\\polyzones.shp"
    arcpy.AddField_management(polyzones, "Lake_ID", "LONG")

    cursor = arcpy.da.InsertCursor(polyzones, ["GRID_CODE", "SHAPE@", "Lake_ID"])


    segmentscursor = arcpy.da.UpdateCursor(str_bufferedsegments, ["GRID_CODE", "SHAPE@"])
    for segment in segmentscursor:
        Xmin = segment[1].extent.XMin
        Ymin = segment[1].extent.YMin
        Xmax = segment[1].extent.XMax
        Ymax = segment[1].extent.YMax
        if segment[0] in toclip:

            if toclip[segment[0]][0] == "Xmin":
                Xmin = max(toclip[segment[0]][1], Xmin)
            if toclip[segment[0]][0] == "Xmax":
                Xmax = min(toclip[segment[0]][1], Xmax)
            if toclip[segment[0]][0] == "Ymin":
                Ymin = max(toclip[segment[0]][1], Ymin)
            if toclip[segment[0]][0] == "Ymax":
                Ymax = min(toclip[segment[0]][1], Ymax)

        segmentscursor.updateRow(segment)

        array = arcpy.Array([arcpy.Point(Xmin, Ymin),
                             arcpy.Point(Xmin, Ymax),
                             arcpy.Point(Xmax, Ymax),
                             arcpy.Point(Xmax, Ymin)])
        polygon = arcpy.Polygon(array)

        if segment[0] in lakes_bci:
            lakeid = lakes_bci[segment[0]]
        else:
            lakeid = -999

        cursor.insertRow([segment[0], polygon, lakeid])

    del cursor
    del segmentscursor


    arcpy.CreateFeatureclass_management(os.path.dirname(save_sourcepoints),
                                        os.path.basename(save_sourcepoints), "POINT",
                                        spatial_reference=flowdir.raster.spatialReference)
    arcpy.AddField_management(save_sourcepoints, "ZoneID", "LONG")
    arcpy.AddField_management(save_sourcepoints, "fpid", "LONG")

    pointcursor = arcpy.da.InsertCursor(save_sourcepoints, ["ZoneID", "fpid", "SHAPE@XY"])
    for pointkey in inputpoints:
        pointcursor.insertRow(
            [pointkey, inputpoints[pointkey].frompointid, (inputpoints[pointkey].X, inputpoints[pointkey].Y)])
    del pointcursor

    return





