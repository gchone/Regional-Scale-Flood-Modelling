# -*- coding: utf-8 -*-

# execute_largeurpartransect by François Larouche-Tremblay, Ing, M Sc

import arcpy
import numpy as np
from os.path import basename
from arcpy.lr import MakeRouteEventLayer
from arcpy.management import AddField, CalculateField, SelectLayerByLocation, MakeFeatureLayer, \
    DeleteIdentical, FeatureVerticesToPoints, JoinField, AlterField, SplitLineAtPoint, CopyFeatures, \
    SelectLayerByAttribute, MultipartToSinglepart, DeleteRows, DeleteField, Merge, PolygonToLine, \
    CreateTable, PointsToLine
from arcpy.analysis import Intersect, Buffer, Statistics, Erase, Near, SpatialJoin
from arcpy.da import NumPyArrayToTable, TableToNumPyArray, FeatureClassToNumPyArray
from DataManagementDEH import addfieldtoarray, deleteuselessfields, getfieldproperty

from tree.FullRiverNetwork import *
import ArcpyGarbageCollector as gc
from InterpolatePoints import *
# import numpy.lib.recfunctions as rfn
from LocatePointsAlongRoutes import *


def pointsdextremites(streamnetwork, idfield, distfield, banklines, endpoints):
    # **************************************************************************
    # DÉFINITION :
    # Génère les extrémités des tronçons en excluant les zones de confluence.
    # Les points sont positionnés à une distance approximative d'une
    # demi-largeur de cours d'eau directement en amont ou en aval des confluences.

    # ENTRÉES :
    # streamnetwork = STRING, chemin d'accès vers le réseau de référencement linéaire
    # banklines = STRING, chemin d'accès vers la ligne de contour du
    #                     polygone des cours d'eau.
    # cellsize = FLOAT, largeur des cellules du MNT utilisé pour le pré-traitement
    # enpoints = STRING, emplacement où seront enregistrés les points d'extrémités

    # SORTIE :
    # enpoints = STRING, les points d'extrémités des branches sont enregistrés.
    # **************************************************************************

    # Création d'un ensemble de points aux extrémités aval des tronçons de confluence
    endpts = gc.CreateScratchName("ptex", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    FeatureVerticesToPoints(streamnetwork, endpts, "END")

    # Création d'un ensemble de points aux extrémités amont des tronçons de confluence
    startpts = gc.CreateScratchName("ptex", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    FeatureVerticesToPoints(streamnetwork, startpts, "START")

    # Création d'un ensemble de points aux extrémités du réseau (sources et exutoire)
    dangpts = gc.CreateScratchName("ptex", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    FeatureVerticesToPoints(streamnetwork, dangpts, "DANGLE")

    # Mise en mémoire de l'exutoire et des points de source
    MakeFeatureLayer(dangpts, "dangpts_lyr")
    SelectLayerByLocation("dangpts_lyr", "INTERSECT", endpts, "", "NEW_SELECTION")

    add_to_stop_pts = gc.CreateScratchName("ptex", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    CopyFeatures("dangpts_lyr", add_to_stop_pts)
    SelectLayerByAttribute("dangpts_lyr", "CLEAR_SELECTION")

    AddField(streamnetwork, distfield, "DOUBLE", field_is_nullable="NULLABLE")
    CalculateField(streamnetwork, distfield, "!SHAPE_LENGTH!", "PYTHON3")
    JoinField(add_to_stop_pts, idfield, streamnetwork, idfield, distfield)

    SelectLayerByLocation("dangpts_lyr", "INTERSECT", startpts, "", "NEW_SELECTION")

    add_to_start_pts = gc.CreateScratchName("ptex", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    CopyFeatures("dangpts_lyr", add_to_start_pts)
    SelectLayerByAttribute("dangpts_lyr", "CLEAR_SELECTION")

    AddField(add_to_start_pts, distfield, "DOUBLE", field_is_nullable="NULLABLE")
    CalculateField(add_to_start_pts, distfield, "0", "PYTHON3")

    keepers = ["OBJECTID", "SHAPE", idfield, distfield]  # On garde seulement les champs nécessaires
    deleteuselessfields(add_to_start_pts, keepers, mapping="FC")
    deleteuselessfields(add_to_stop_pts, keepers, mapping="FC")

    # Suppression des points aval qui ne sont pas des confluences (fin à l'exutoire)
    MakeFeatureLayer(endpts, "endpts_lyr")
    SelectLayerByLocation("endpts_lyr", "INTERSECT", dangpts, "", "NEW_SELECTION")
    DeleteRows("endpts_lyr")
    SelectLayerByAttribute("endpts_lyr", "CLEAR_SELECTION")

    # Suppression des points amont qui ne sont pas des confluences (départ à 0)
    MakeFeatureLayer(startpts, "startpts_lyr")
    SelectLayerByLocation("startpts_lyr", "INTERSECT", dangpts, "", "NEW_SELECTION")
    DeleteRows("startpts_lyr")
    SelectLayerByAttribute("startpts_lyr", "CLEAR_SELECTION")

    # Calcul de la distance des points de confluence (amont et aval) avec la berge la plus proche afin de créer
    # un buffer qui s'adapte à la forme de la confluence pour positionner les premiers et derniers transects
    Near(endpts, banklines, None, "NO_LOCATION", "NO_ANGLE", "PLANAR")
    AddField(endpts, "Buff_dist", "FLOAT")
    # HARDCODED : Il est préférable de prendre 2 fois le cellsize du MNT utilisé pour le pré-traitement.
    cellsize = 4  # Résolution du MNT
    CalculateField(endpts, "Buff_dist", "!NEAR_DIST! + {0}".format(2 * cellsize), "PYTHON3")

    Near(startpts, banklines, None, "NO_LOCATION", "NO_ANGLE", "PLANAR")
    AddField(startpts, "Buff_dist", "FLOAT")
    CalculateField(startpts, "Buff_dist", "!NEAR_DIST! + {0}".format(2 * cellsize), "PYTHON3")

    # Suppression des champs inutiles
    keepers2 = ["OBJECTID", "SHAPE", idfield, "Buff_dist"]  # On garde seulement les champs nécessaires
    deleteuselessfields(endpts, keepers2, mapping="FC")
    deleteuselessfields(startpts, keepers2, mapping="FC")

    # Création d'un ensemble de points situés immédiatement en amont ou en aval des points de confluence
    end_buffer = gc.CreateScratchName("ptex", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    Buffer(endpts, end_buffer, "Buff_dist", "FULL", "ROUND", "NONE", "", "PLANAR")
    AlterField(end_buffer, idfield, "Select_id", "Select_id")

    start_buffer = gc.CreateScratchName("ptex", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    Buffer(startpts, start_buffer, "Buff_dist", "FULL", "ROUND", "NONE", "", "PLANAR")
    AlterField(start_buffer, idfield, "Select_id", "Select_id")

    end_buffer_lines = gc.CreateScratchName("ptex", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    Intersect([end_buffer, streamnetwork], end_buffer_lines, "ALL", "", "LINE")

    start_buffer_lines = gc.CreateScratchName("ptex", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    Intersect([start_buffer, streamnetwork], start_buffer_lines, "ALL", "", "LINE")

    # Suppression des champs inutiles pour ne pas qu'ils puissent interférer avec le traitement
    keepers3 = ["OBJECTID", "SHAPE", "SHAPE_LENGTH", idfield, "Select_id"]  # On garde seulement les champs nécessaires
    deleteuselessfields(end_buffer_lines, keepers3, mapping="FC")
    deleteuselessfields(start_buffer_lines, keepers3, mapping="FC")

    AddField(end_buffer_lines, "SELECT_FIELD", "LONG", field_is_nullable="NULLABLE")
    CalculateField(end_buffer_lines, "SELECT_FIELD", "!Select_id! == !{0}!".format(idfield), "PYTHON3")

    AddField(start_buffer_lines, "SELECT_FIELD", "LONG", field_is_nullable="NULLABLE")
    CalculateField(start_buffer_lines, "SELECT_FIELD", "!Select_id! == !{0}!".format(idfield), "PYTHON3")

    # Suppression des segments aval qui ne correspondent à aucune branche
    MakeFeatureLayer(start_buffer_lines, "start_buffer_lines_lyr")
    SelectLayerByAttribute("start_buffer_lines_lyr", "NEW_SELECTION", '"SELECT_FIELD" = 0', "")
    DeleteRows("start_buffer_lines_lyr")
    SelectLayerByAttribute("start_buffer_lines_lyr", "CLEAR_SELECTION")

    start_points = gc.CreateScratchName("ptex", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    FeatureVerticesToPoints(start_buffer_lines, start_points, "END")

    AddField(start_buffer_lines, distfield, "DOUBLE", field_is_nullable="NULLABLE")
    CalculateField(start_buffer_lines, distfield, "!SHAPE_LENGTH!", "PYTHON3")
    JoinField(start_points, idfield, start_buffer_lines, idfield, distfield)

    # Suppression des segments amont qui ne correspondent à aucune branche
    MakeFeatureLayer(end_buffer_lines, "end_buffer_lines_lyr")
    SelectLayerByAttribute("end_buffer_lines_lyr", "NEW_SELECTION", '"SELECT_FIELD" = 0', "")
    DeleteRows("end_buffer_lines_lyr")
    SelectLayerByAttribute("end_buffer_lines_lyr", "CLEAR_SELECTION")

    stop_points = gc.CreateScratchName("ptex", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    FeatureVerticesToPoints(end_buffer_lines, stop_points, "START")

    AlterField(streamnetwork, distfield, "Destination", "Destination")
    JoinField(stop_points, idfield, streamnetwork, idfield, "Destination")
    DeleteField(streamnetwork, "Destination")

    AddField(end_buffer_lines, "Restant", "DOUBLE", field_is_nullable="NULLABLE")
    CalculateField(end_buffer_lines, "Restant", "!SHAPE_LENGTH!", "PYTHON3")
    JoinField(stop_points, idfield, end_buffer_lines, idfield, "Restant")

    AddField(stop_points, distfield, "DOUBLE", field_is_nullable="NULLABLE")
    CalculateField(stop_points, distfield, "!Destination! - !Restant!", "PYTHON3")

    deleteuselessfields(start_points, keepers, mapping="FC")
    deleteuselessfields(stop_points, keepers, mapping="FC")

    Merge([start_points, stop_points, add_to_start_pts, add_to_stop_pts], endpoints)

    return


def pointsdemesure(streamnetwork, idfield, csfield, distfield, spacing, datapoints, endpoints=None):
    # **************************************************************************
    # DÉFINITION :
    # Génère les extrémités des tronçons en excluant les zones de confluence.
    # Les points sont positionnés à une distance approximative d'une
    # demi-largeur de cours d'eau directement en amont ou en aval des confluences.

    # ENTRÉES :
    # streamnetwork = STRING, chemin d'accès vers le réseau de référencement linéaire
    # idfield = STRING, nom du champ contenant les identifiants de tronçons
    # csfield = STRING, nom du champ qui contiendra un identifiant unique de point (Exemple: "CSid")
    # distfield = STRING, nom du champ qui contiendra la distance par rapport à l'amont (Exemple: "Distance_m")
    # spacing = FLOAT, espacement entre les points de mesure
    # datapoints = STRING, emplacement où seront enregistrés les points de mesure
    # enpoints = STRING, chemin d'accès vers les points d'extrémités

    # offset=0, possibilité d'ajouter un offset pour tester la sensibilité du placement des sections

    # SORTIE :
    # datapoints = STRING, les points de mesure sont enregistrés.
    # **************************************************************************

    idln = FeatureClassToNumPyArray(streamnetwork, [idfield, "SHAPE@LENGTH"], null_value=-9999)
    forkid = idln[idfield]
    length = idln["SHAPE@LENGTH"]
    strt = np.repeat(spacing, length.shape)  # np.zeros(length.shape)
    stop = np.copy(length) - spacing  # Pour éviter que les transects soient directement aux extrémités

    # Afin d'exclure les zones de confluence, les points sont générés entre les points d'extrémités (inclus)
    # Si les points d'extrémités ne sont pas spécifiés, les points de mesure sont générés sur toute la longueur.
    if endpoints is not None:
        endarr = TableToNumPyArray(endpoints, [idfield, distfield], null_value=-9999)
        for i in range(0, forkid.shape[0], 1):
            ends = endarr[distfield][endarr[idfield] == forkid[i]]
            if ends.shape[0] >= 1:
                strt[i] = np.min(ends)
                stop[i] = np.max(ends)

        # Ajustement pour les points d'extrémité manquants
        ratio = np.divide(strt, length)
        temp_strt = 1000 * strt + 0.5
        temp_stop = 1000 * stop + 0.5
        int_strt = temp_strt.astype(int)
        int_stop = temp_stop.astype(int)
        con1 = np.logical_and(int_strt == int_stop, ratio >= 0.5)
        con2 = np.logical_and(int_strt == int_stop, ratio < 0.5)
        strt[con1] = spacing  # au lieu de 0
        stop[con2] = length[con2] - spacing

        con3 = (strt == 0)
        temp_length = 1000 * length + 0.5
        int_length = temp_length.astype(int)
        con4 = (int_stop == int_length)
        strt[con3] = spacing
        stop[con4] = length[con4] - spacing

    # Requête des paramètres du champ idfield
    idft = getfieldproperty(streamnetwork, idfield, "type", default="STRING")
    if idft == "STRING":
        idft = "TEXT"

    # Création des champs dans la table vide
    temptabl = gc.CreateScratchName("table", data_type="ArcInfoTable", workspace=arcpy.env.scratchWorkspace)
    CreateTable(arcpy.env.scratchWorkspace, basename(temptabl))  # Champ OBJECTID créé avec la table

    fieldnames = [csfield, distfield, idfield]
    for field, dtype in zip(fieldnames, ["LONG", "FLOAT", idft]):
        AddField(temptabl, field, dtype)

    s1arr = TableToNumPyArray(temptabl, fieldnames, null_value=-9999)
    arrlist = []
    trows = 0
    dt1 = s1arr.dtype
    for sa, so, fkid in zip(strt, stop, forkid):
        if (so - sa) < 0:
            arcpy.AddMessage("La branche {0} est trop courte ou à l'envers, elle ne peut être traitée.".format(fkid))
            continue

        if (so - sa) < (3 * spacing):
            arcpy.AddMessage("La branche {0} est courte, l'espacement ne sera pas respecté.".format(fkid))
            dist = np.arange(sa, so + 0.0001, (so - sa)/3)  # Position par rapport à l'amont de la branche
        else:
            arcpy.AddMessage("La branche {0} a été traitée avec succès.".format(fkid))
            dist = np.arange(sa, so, spacing)  # Position par rapport à l'amont de la branche de chaque transect

        if (so - dist[-1]) > (spacing / 2):  # Dernier transect déplacé ou ajouté
            dist = np.append(dist, so)
        else:
            dist[-1] = so

        nrows = dist.shape[0]
        trows += nrows
        newblock = np.repeat(np.array([(0, 0, fkid)], dtype=dt1), nrows)
        newblock[distfield] = dist
        arrlist.append(newblock)

    s1arr = np.concatenate(arrlist)
    s1arr[csfield] = np.arange(1, trows + 1, 1)
    s1evnt = gc.CreateScratchName("table", data_type="ArcInfoTable", workspace=arcpy.env.scratchWorkspace)
    NumPyArrayToTable(s1arr, s1evnt)

    eventtype = "{0} Point {1}".format(idfield, distfield)
    MakeRouteEventLayer(streamnetwork, idfield, s1evnt, eventtype, "s1evnt_lyr", None)
    CopyFeatures("s1evnt_lyr", datapoints)  # Enregistre les points de repère de distance et le type de chaque CS

    return


def transectsauxpointsdemesure(streamnetwork, idfield, cspoints, csfield, distfield, maxwidth, riverbanks, transects):
    # **************************************************************************
    # DÉFINITION :
    # Génère des transects rectilignes sur toutes les branches du réseau à
    # chacun des points de mesure fournit en entrée, en excluant les confluences.

    # ENTRÉES :
    # streamnetwork = STRING, chemin d'accès vers le réseau de référencement linéaire
    # idfield = STRING, nom du champ contenant les identifiants de tronçons
    # cspoints = STRING, chemin d'accès vers les points de positionnement des
    #                    transects. Les points doivent contenir un champ qui
    #                    indique le type des transects, soit:
    #                    CSTYPE : Normal = 1, Confluence = 0, Start = 2, Stop = 3
    # csfield = STRING, nom du champ qui contiendra un identifiant unique de point (Exemple: "CSid")
    # distfield = STRING, nom du champ qui contiendra la distance par rapport à l'amont (Exemple: "Distance_m")
    # maxwidth = FLOAT, largeur maximale des transects
    # riverbanks = STRING, chemin d'accès vers les lignes de berge des cours d'eau; les transects
    #                    seront contenus à l'intérieur des berges
    # transects = STRING, emplacement où seront enregistrés les transects

    # SORTIE :
    # transects = STRING, les transects sont enregistrés sous forme de lignes
    # **************************************************************************

    csarr = TableToNumPyArray(cspoints, [csfield, idfield, distfield], null_value=-9999)
    csarr = np.sort(csarr, order=csfield)  # Au cas où l'ordre des points aurait été mélangé

    # On ajoute le champ et les valeurs de offset pour générer les évènements de chaque côté du réseau
    ofstfield = "Offset"
    transarr = addfieldtoarray(np.repeat(csarr, 2), (ofstfield, '<f8'))  # Deux points pour chaque transects
    transarr[ofstfield] = np.tile([maxwidth / 2, -maxwidth / 2], csarr.shape[0])

    # Création des transects en reliant les points générés de part et d'autre du réseau de cours d'eau
    transevnt = gc.CreateScratchName("table", data_type="ArcInfoTable", workspace=arcpy.env.scratchWorkspace)
    NumPyArrayToTable(transarr, transevnt)

    eventtype = "{0} Point {1}".format(idfield, distfield)
    MakeRouteEventLayer(streamnetwork, idfield, transevnt, eventtype, "transevnt_lyr", offset_field=ofstfield)
    # GC: ajout d'un fichier temporaire car PointsToLine bug avec une layer en input
    ptsfortrans = gc.CreateScratchName("trpt", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    arcpy.CopyFeatures_management("transevnt_lyr", ptsfortrans)

    rawtrans = gc.CreateScratchName("trpt", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    #PointsToLine("transevnt_lyr", rawtrans, csfield, "", "NO_CLOSE")
    PointsToLine(ptsfortrans, rawtrans, csfield, "", "NO_CLOSE")

    AlterField(rawtrans, csfield, "Select_id", "Select_id")

    transends = gc.CreateScratchName("trpt", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    Intersect([rawtrans, riverbanks], transends, "ONLY_FID", "", "POINT")

    # Découpage des transects brutes en fonction des lignes de berges
    split_transects = gc.CreateScratchName("trpt", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    SplitLineAtPoint(rawtrans, transends, split_transects, "0.05 Meters")

    # Comparaison avec le csid afin de générer un champ pour la sélection
    # Sélection des transects et suppression des lignes situées à l'extérieur des lignes de berge
    fms = arcpy.FieldMappings()
    fms.addTable(cspoints)
    fms.addTable(split_transects)
    SpatialJoin(split_transects, cspoints, transects, "JOIN_ONE_TO_ONE", "KEEP_ALL", fms,
                "WITHIN_A_DISTANCE", "0.1 Meters", None)
    AddField(transects, "SELECT_FIELD", "LONG", field_is_nullable="NULLABLE")
    CalculateField(transects, "SELECT_FIELD", "!Select_id! == !{0}!".format(csfield), "PYTHON3")

    # Suppression des retailles de transects qui ne correspondent à aucun point
    MakeFeatureLayer(transects, "transects_lyr")
    SelectLayerByLocation("transects_lyr", "INTERSECT", cspoints, "0.1 Meters", "NEW_SELECTION", "INVERT")
    SelectLayerByAttribute("transects_lyr", "ADD_TO_SELECTION", '"SELECT_FIELD" = 0', "")
    DeleteRows("transects_lyr")
    SelectLayerByAttribute("transects_lyr", "CLEAR_SELECTION")

    # Suppression des champs inutiles
    keepers = ["SHAPE_LENGTH", "OBJECTID", "SHAPE"]
    deleteuselessfields(transects, keepers, mapping="FC")

    return


def transectsverspoints(transects, datapoints):
    # **************************************************************************
    # DÉFINITION :
    # Transfert les données contenues dans la table d'attribut des transects
    # vers les points de mesure

    # ENTRÉES :
    # transects = STRING, chemin d'accès vers les transects (polyline)
    # datapoints = STRING, chemin d'accès vers les points de positionnement des
    #                      transects.
    # tol = STRING, portée (en m) pour le SpatialJoin

    # SORTIE :
    # La table d'attribut des datapoints est modifiée pour y ajouter les données
    # contenues dans les transects. Seuls les points correspondant à des transects
    # sont conservés.
    # **************************************************************************

    fieldnames = [f.name for f in arcpy.ListFields(datapoints)] + [f.name for f in arcpy.ListFields(transects)]
    fms = arcpy.FieldMappings()  # Table d'attribut suite au SpatialJoin
    fms.addTable(transects)

    oldpts = gc.CreateScratchName("trpt", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    CopyFeatures(datapoints, oldpts)

    MakeFeatureLayer(oldpts, "datapts_lyr")
    SelectLayerByLocation("datapts_lyr", "INTERSECT", transects, "0.1 Meters", "NEW_SELECTION")
    fms.addTable("datapts_lyr")

    tol = 1
    # HARDCODED : Portée (en m) pour le SpatialJoin. Puisque les points de mesure sont normalement situés
    # presque directement sur les transects, une tolérance de 1 m est suffisante
    # Attention, le spacing entre les transects doit être supérieur à la portée.

    SpatialJoin("datapts_lyr", transects, datapoints, "JOIN_ONE_TO_ONE",
                "KEEP_ALL", fms, "WITHIN_A_DISTANCE", "{0} Meters".format(tol), None)

    deleteuselessfields(datapoints, fieldnames, mapping="FC")

    return


def largeurdestransects(streamnetwork, transects, widthfield):
    # **************************************************************************
    # DÉFINITION :
    # Génère des transects équidistants sur chacune des branches du réseau de
    # cours d'eau ainsi que des transects en pointes aux confluences et produit
    # un ensemble de point contenant la largeur des cours d'eau aux transects

    # ENTRÉES :
    # streamnetwork = STRING, chemin d'accès vers le réseau de référencement linéaire
    # idfield = STRING, nom du champ contenant les identifiants de tronçons
    # riverbed = STRING, chemin d'accès vers le polygone des cours d'eau;
    #                    les transects seront contenus dans ce polygone
    # cellsize = FLOAT, largeur des cellules du MNT utilisé pour le pré-traitement
    # maxwidth = FLOAT, largeur maximale des transects
    # spacing = FLOAT, espacement régulier entre les sections (en m)
    # transects = STRING, emplacement où seront enregistrés les transects (Polyline)
    # widthpts = STRING, emplacement où seront enregistrés les points contenant
    #                    la largeur aux transects
    # ineffarea = STRING, chemin d'accès vers les polygones qui masquent
    #                     les zones d'écoulement ineffectives

    # SORTIE :
    # Les couches des transects est des points contenant la largeur aux
    # transects sont enregistrées.
    # **************************************************************************

    # **************************************************************************
    mflag = arcpy.env.outputMFlag

    arcpy.env.outputMFlag = "Disabled"  # Pour que DeleteIdentical fonctionne aux confluences

    # Nettoyage des transects qui traversent deux chenaux ou plus
    overlaps = gc.CreateScratchName("latr", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    Intersect([transects, streamnetwork], overlaps, "ALL", "", "POINT")

    singols = gc.CreateScratchName("latr", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
    MultipartToSinglepart(overlaps, singols)

    DeleteIdentical(singols, ["Shape"])  # Les transects aux confluences génèrent des doublons

    tabletemp = gc.CreateScratchName("table", data_type="ArcInfoTable", workspace=arcpy.env.scratchWorkspace)

    fname = "FID_{0}".format(basename(transects))
    Statistics(singols, tabletemp, [["{0}".format(fname), "COUNT"]], fname)

    MakeFeatureLayer(transects, "transects_lyr")
    JoinField("transects_lyr", "OBJECTID", tabletemp, fname, "COUNT_{0}".format(fname))
    AlterField("transects_lyr", "COUNT_{0}".format(fname), "Bad_Ori")
    SelectLayerByAttribute("transects_lyr", "NEW_SELECTION", '"Bad_Ori" >= 2', "")
    desc = arcpy.Describe("transects_lyr")
    if desc.FIDSet != "":
        DeleteRows("transects_lyr")

    SelectLayerByAttribute("transects_lyr", "CLEAR_SELECTION")
    DeleteField(transects, "Bad_Ori")  # On supprime le champ temporaire

    # Ajout d'un champ pour le calcul de la largeur
    AddField(transects, widthfield, "FLOAT", field_alias=widthfield, field_is_nullable="NULLABLE")
    CalculateField(transects, widthfield, "!Shape_Length!", "PYTHON3")

    arcpy.env.outputMFlag = mflag  # L'environnement est remis à son état initial

    return


def supprimercroisements(transects, nx):
    # **************************************************************************
    # DÉFINITION :
    # Boucle de nettoyage des transects mal orientés ou avec trop de croisements
    #
    # ENTREES :
    # transects = STRING, chemin d'accès vers les transects (polyline)
    # nx = INTEGER, nombre de croisements toléré
    #
    # SORTIES :
    # Les transects avec trop de croisements sont supprimés.
    # **************************************************************************

    fname = "FID_{0}".format(basename(transects))
    MakeFeatureLayer(transects, "transects_lyr")
    for ii in range(5, nx, -1):
        overlaps = gc.CreateScratchName("msucr", data_type="FeatureClass", workspace="in_memory")
        Intersect("transects_lyr", overlaps, "ONLY_FID", "", "POINT")

        tabletemp = gc.CreateScratchName("table", data_type="ArcInfoTable", workspace="in_memory")
        Statistics(overlaps, tabletemp, [[fname, "COUNT"]], fname)
        gc.AddToGarbageBin(tabletemp)
        JoinField("transects_lyr", "OBJECTID", tabletemp, fname, "COUNT_{0}".format(fname))
        SelectLayerByAttribute("transects_lyr", "NEW_SELECTION", '"COUNT_{0}" >= {1}'.format(fname, ii), "")
        desc = arcpy.Describe("transects_lyr")
        if desc.FIDSet != "":
            DeleteRows("transects_lyr")

        SelectLayerByAttribute("transects_lyr", "CLEAR_SELECTION")
        DeleteField("transects_lyr", "COUNT_{0}".format(fname))  # On supprime le champ temporaire

    return


def execute_largeurpartransect(streamnetwork, idfield, riverbed, ineffarea, maxwidth,
                               spacing, transects, cspoints, messages):
    # **************************************************************************
    # DÉFINITION :
    # Corps d'exécution (main) de l'outil de calcul de la largeur des cours d'eau.

    # ENTRÉES :
    # streamnetwork = STRING, chemin d'accès vers le réseau de référencement linéaire
    # idfield = STRING, nom du champ contenant les identifiants de tronçons
    # riverbed = STRING, chemin d'accès vers le polygone des cours d'eau;
    #                    les transects seront contenus dans ce polygone
    # ineffarea = STRING, chemin d'accès vers les polygones qui masquent
    #                     les zones d'écoulement ineffectives
    # maxwidth = FLOAT, largeur maximale des transects
    # spacing = FLOAT, espacement régulier entre les sections (en m)
    # transects = STRING, emplacement où seront enregistrés les transects (Polyline)
    # cspoints = STRING, emplacement où seront enregistrés les points contenant
    #                    la largeur aux transects

    # SORTIE :
    # Les couches des transects est des points contenant la largeur aux
    # transects sont enregistrées.
    # **************************************************************************

    # Paramètres d'environnement et de gestion des couches temporaires

    try:
        # Suppression des zones d'écoulement ineffectives
        if ineffarea and ineffarea != "#":
            effbed = gc.CreateScratchName("mmexlt", data_type="FeatureClass", workspace="in_memory")
            Erase(riverbed, ineffarea, effbed)
            inpoly = effbed
        else:
            inpoly = riverbed

        csfield, distfield = "CSid", "Distance_m"  # HARDCODED

        # Création des lignes des berges de cours d'eau
        riverbanks = gc.CreateScratchName("mmexlt", data_type="FeatureClass", workspace="in_memory")
        PolygonToLine(inpoly, riverbanks, "IGNORE_NEIGHBORS")

        # Création d'un ensemble de points situés immédiatement en amont et en aval des points de confluence
        endcs = gc.CreateScratchName("mexlt", data_type="FeatureClass", workspace="in_memory")
        pointsdextremites(streamnetwork, idfield, distfield, riverbanks, endcs)

        # Création de l'ensemble de points où sera mesurée la largeur sur le réseau (entre les points d'extrémités)
        pointsdemesure(streamnetwork, idfield, csfield, distfield, spacing, cspoints, endcs)

        # Création des transects équidistants situés sur les branches de cours d'eau
        transectsauxpointsdemesure(streamnetwork, idfield, cspoints, csfield, distfield,
                                   maxwidth, riverbanks, transects)

        widthfield = "Width_m"  # HARDCODED
        largeurdestransects(streamnetwork, transects, widthfield)

        nx = 2  # Nombre de croisements tolérés
        supprimercroisements(transects, nx)

        transectsverspoints(transects, cspoints)

    finally:
        # Suppression des couches de données temporaires
        gc.CleanAllTempFiles()

    return


def execute_WidthPostProc(network_shp, RID_field, main_channel_field, network_main_only, RID_field_main, network_main_l_field, order_field, network_main_only_links, widthdata, widthid, width_RID_field, width_distance, width_field, datapoints, id_field_datapts, distance_field_datapts, rid_field_datapts, ouput_shp, messages):
    try:
        messages.addMessage("Processing main channels")
        ### 1a - Project points in the main channel on the main_only network
        # Selection only the points on the main channels
        arcpy.MakeFeatureLayer_management(widthdata, "width_main_lyr")
        arcpy.AddJoin_management("width_main_lyr", width_RID_field, network_shp, RID_field)
        arcpy.SelectLayerByAttribute_management("width_main_lyr", "NEW_SELECTION",
                                                arcpy.Describe(network_shp).basename + "." + main_channel_field + " = 1")
        # Linear reference them on the network_main_only

        main_width_pts = gc.CreateScratchName("pts", data_type="ArcInfoTable", workspace="in_memory")
        arcpy.MakeFeatureLayer_management(network_shp, "network_lyr")
        arcpy.SelectLayerByAttribute_management("network_lyr", "NEW_SELECTION",
                                                main_channel_field + " = 1")
        splitted_to_unsplitted("network_lyr", RID_field, "width_main_lyr", widthid, width_RID_field, width_distance, width_field, network_main_only, RID_field_main, network_main_l_field, main_width_pts)

        ### 1b - Interpolate width data on datapoints

        network = RiverNetwork()
        network.dict_attr_fields['id'] = RID_field_main
        network.dict_attr_fields['order'] = order_field
        network.load_data(network_main_only, network_main_only_links)

        width_pts_collection = Points_collection(network, "data")
        width_pts_collection.dict_attr_fields['id'] = widthid
        width_pts_collection.dict_attr_fields['reach_id'] = RID_field_main
        width_pts_collection.dict_attr_fields['dist'] = width_distance
        width_pts_collection.dict_attr_fields['width'] = width_field
        width_pts_collection.load_table(main_width_pts)


        targetcollection = Points_collection(network, "target")
        targetcollection.dict_attr_fields['id'] = id_field_datapts
        targetcollection.dict_attr_fields['reach_id'] = rid_field_datapts
        targetcollection.dict_attr_fields['dist'] = distance_field_datapts
        targetcollection.load_table(datapoints)

        interp_main_width_pts_np = InterpolatePoints_with_objects(network, width_pts_collection, [width_field], targetcollection, "CONFLUENCE")


        ### 2a - Project width point of secondary channels on the main_only network
        arcpy.MakeFeatureLayer_management(widthdata, "width_second_lyr")
        arcpy.AddJoin_management("width_second_lyr", width_RID_field, network_shp, RID_field)
        arcpy.SelectLayerByAttribute_management("width_second_lyr", "NEW_SELECTION",
                                                arcpy.Describe(network_shp).basename + "." + main_channel_field + " = 0")


        secondary_width_pts = gc.CreateScratchName("pts", data_type="ArcInfoTable", workspace=arcpy.env.scratchWorkspace)

        # Points on secondary channels are projected on the closest main channel
        arcpy.LocateFeaturesAlongRoutes_lr("width_second_lyr", network_main_only, RID_field_main, 10000, secondary_width_pts,
                                         RID_field_main + " POINT MEAS", distance_field="NO_DISTANCE")



        ### 2b - Interpolate width data for every secondary channel (with 0 upstream and downstream of the secondary channel)
        ### 3 - Sum all width measurements
        secondary_channel_RID_field = [f.name for f in arcpy.ListFields(secondary_width_pts)][
            [f.name for f in arcpy.ListFields("width_main_lyr")].index(
                arcpy.Describe(widthdata).basename + "." + width_RID_field) + 1]
        secondary_width_pts_np = arcpy.da.TableToNumPyArray(secondary_width_pts, [widthid, RID_field_main, "MEAS", width_field, secondary_channel_RID_field])
        secondary_RIDs = np.unique(secondary_width_pts_np[[secondary_channel_RID_field]])


        interp_main_width_pts_np = np.sort(interp_main_width_pts_np, order=id_field_datapts) # ordering to ensure match latter

        datacollection = Points_collection(network, "data")
        datacollection.dict_attr_fields['id'] = widthid
        datacollection.dict_attr_fields['reach_id'] = RID_field_main
        datacollection.dict_attr_fields['dist'] = "MEAS"
        datacollection.dict_attr_fields['width'] = width_field
        datacollection.dict_attr_fields[secondary_channel_RID_field] = secondary_channel_RID_field
        datacollection.load_table(secondary_width_pts)

        fullnetwork = FullRiverNetwork()
        fullnetwork.dict_attr_fields['id'] = RID_field_main

        fullnetwork.load_data(network_shp)
        width_pts_collection2 = Points_collection(fullnetwork, "data")
        width_pts_collection2.dict_attr_fields['id'] = widthid
        width_pts_collection2.dict_attr_fields['reach_id'] = RID_field_main
        width_pts_collection2.dict_attr_fields['dist'] = width_distance
        width_pts_collection2.dict_attr_fields['width'] = width_field
        width_pts_collection2.load_table(widthdata)



        i=0
        for rid in secondary_RIDs:
            i+=1
            messages.addMessage("Processing secondary channels (" + str(i) + "/" + str(len(secondary_RIDs)) + ")")
            # take secondary channel points
            subdatasample = datacollection._numpyarray[datacollection._numpyarray[secondary_channel_RID_field] == rid[0]]
            # make sure they are ordered
            subdatasample = np.sort(subdatasample, order=datacollection.dict_attr_fields['dist'])

            # look for reach inversion (secondary channel with points, once projected on the main channel, inverted)
            # Look for the distance between the first and the last point
            projecteddownpt = secondary_width_pts_np[secondary_width_pts_np[widthid] == fullnetwork.get_reach(rid[0]).get_first_point(width_pts_collection2).id]
            projecteduppt = secondary_width_pts_np[secondary_width_pts_np[widthid] == fullnetwork.get_reach(rid[0]).get_last_point(width_pts_collection2).id]
            currentreach = network.get_reach(projecteduppt[RID_field_main])
            while ((not currentreach.is_downstream_end()) and currentreach.id != projecteddownpt[RID_field_main]):
                currentreach = currentreach.get_downstream_reach()
            inverted = (currentreach.id != projecteddownpt[RID_field_main] or projecteddownpt[datacollection.dict_attr_fields['dist']] > projecteduppt[datacollection.dict_attr_fields['dist']])

            if inverted:
                tmpswitch = projecteddownpt
                projecteddownpt = projecteduppt
                projecteduppt = tmpswitch

            # add the furthest point between the first points on the upstream reaches.
            # list these points in the full network
            if not inverted:
                extremity_pts = fullnetwork.get_reach(rid[0]).get_upstreamnextpts(width_pts_collection2)
            else:
                extremity_pts = fullnetwork.get_reach(rid[0]).get_downstreamnextpts(width_pts_collection2)
            # find the equivalent in the projected point on the main network...
            upprojectedpts = secondary_width_pts_np[np.in1d(secondary_width_pts_np[widthid], np.array([p.id for p in extremity_pts]))]
            upprojectedpts = upprojectedpts[[widthid, RID_field_main, "MEAS", width_field]]
            # ... or on the main network width points (downprojectedpts2)


            # Look for the distance to the most upstream
            maxdist = 0
            furthestpt = None

            for pt in upprojectedpts:
                reach = network.get_reach(pt[RID_field_main])
                reachdist = 0
                while(reach.id != projecteduppt[RID_field_main]):
                    if reach.is_downstream_end():
                        raise IndexError
                    reach = reach.get_downstream_reach()
                    reachdist += reach.length
                distance = pt[datacollection.dict_attr_fields['dist']] - projecteduppt[datacollection.dict_attr_fields['dist']] + reachdist
                if distance>maxdist:
                    distfield = datacollection.dict_attr_fields['dist']
                    maxdist = distance
                    furthestpt = pt

            upprojectedpts2 = width_pts_collection._numpyarray[
                np.in1d(width_pts_collection._numpyarray[widthid], np.array([p.id for p in extremity_pts]))]


            for pt in upprojectedpts2:
                reach = network.get_reach(pt[RID_field_main])
                reachdist = 0
                while(reach.id != projecteduppt[RID_field_main]):
                    if reach.is_downstream_end():
                        raise IndexError
                    reach = reach.get_downstream_reach()
                    reachdist += reach.length
                distance = pt[width_pts_collection.dict_attr_fields['dist']] - projecteduppt[datacollection.dict_attr_fields['dist']] + reachdist
                if distance>maxdist:
                    distfield = width_pts_collection.dict_attr_fields['dist']
                    maxdist = distance
                    furthestpt = pt

            # in some specific cases, the points passed the confluence are not further than the last point on the
            # secondary channel. This should not happen often.
            if furthestpt is not None:
                # add the point to datacollection as
                newpt = network.get_reach(furthestpt[RID_field_main]).add_point(furthestpt[distfield], datacollection)
                # assign 0 to the width of the furthest point for interpolation
                newpt.width = 0
                # add the point to the subdatasample
                furthestpt_np = network.points_collection[datacollection.name]._numpyarray[network.points_collection[datacollection.name]._numpyarray[widthid] == newpt.id]
                subdatasample = np.concatenate((subdatasample, furthestpt_np))

            # refaire pour l'autre extremité

            # add the furthest point between the last points on the downstream reaches.
            # list these points in the full network
            if not inverted:
                extremity_pts = fullnetwork.get_reach(rid[0]).get_downstreamnextpts(width_pts_collection2)
            else:
                extremity_pts = fullnetwork.get_reach(rid[0]).get_upstreamnextpts(width_pts_collection2)

            # find the equivalent in the projected point on the main network...
            downprojectedpts = secondary_width_pts_np[
                np.in1d(secondary_width_pts_np[widthid], np.array([p.id for p in extremity_pts]))]
            downprojectedpts = downprojectedpts[[widthid, RID_field_main, "MEAS", width_field]]
            # ... or on the main network width points (downprojectedpts2)

            # Look for the distance to the most downstream
            maxdist = 0
            furthestpt = None
            for pt in downprojectedpts:
                reach = network.get_reach(projecteddownpt[RID_field_main])
                reachdist = 0
                skip_pt = False
                while (reach.id != pt[RID_field_main]):
                    if reach.is_downstream_end():
                        # The reach of the projected point was not found downstream
                        # It means it comes from a tributary and must be skipped
                        skip_pt = True
                        break
                    reach = reach.get_downstream_reach()
                    reachdist += reach.length
                if skip_pt:
                    continue
                distance = projecteddownpt[
                    datacollection.dict_attr_fields['dist']] - pt[datacollection.dict_attr_fields['dist']] + reachdist
                if distance > maxdist:
                    distfield = datacollection.dict_attr_fields['dist']
                    maxdist = distance
                    furthestpt = pt



            downprojectedpts2 = width_pts_collection._numpyarray[
                np.in1d(width_pts_collection._numpyarray[widthid], np.array([p.id for p in extremity_pts]))]

            for pt in downprojectedpts2:
                reach = network.get_reach(projecteddownpt[RID_field_main])
                reachdist = 0
                skip_pt = False
                while (reach.id != pt[RID_field_main]):
                    if reach.is_downstream_end():
                        # The reach of the projected point was not found downstream
                        # It means it comes from a tributary and must be skipped
                        skip_pt = True
                        break
                    reach = reach.get_downstream_reach()
                    reachdist += reach.length
                if skip_pt:
                    continue
                distance = projecteddownpt[
                    datacollection.dict_attr_fields['dist']] - pt[width_pts_collection.dict_attr_fields['dist']] + reachdist
                if distance > maxdist:
                    distfield = width_pts_collection.dict_attr_fields['dist']
                    maxdist = distance
                    furthestpt = pt

            # in some specific cases, the points passed the confluence are not further than the last point on the
            # secondary channel. This should not happen often.
            if furthestpt is not None:
                # add the point to datacollection as
                newpt = network.get_reach(furthestpt[RID_field_main]).add_point(furthestpt[distfield], datacollection)
                # assign 0 to the width of the furthest point for interpolation
                newpt.width = 0
                # add the point to the subdatasample
                furthestpt_np = network.points_collection[datacollection.name]._numpyarray[
                    network.points_collection[datacollection.name]._numpyarray[widthid] == newpt.id]
                subdatasample = np.concatenate((subdatasample, furthestpt_np))


            tmp_np = InterpolatePoints_with_objects(network, datacollection, [width_field], targetcollection, 0,
                                            subdatasample=subdatasample)

            tmp_np = np.sort(tmp_np, order=id_field_datapts)
            interp_main_width_pts_np[width_field] = interp_main_width_pts_np[width_field]+tmp_np[width_field]

        if arcpy.env.overwriteOutput and arcpy.Exists(ouput_shp):
            arcpy.Delete_management(ouput_shp)


        temp_outtable = gc.CreateScratchName("outtable", data_type="ArcInfoTable", workspace="in_memory")
        arcpy.da.NumPyArrayToTable(interp_main_width_pts_np, temp_outtable)
        arcpy.MakeRouteEventLayer_lr(network_main_only, RID_field_main, temp_outtable,
                                     rid_field_datapts + " POINT " + distance_field_datapts, "pts_lyr")
        arcpy.CopyFeatures_management("pts_lyr", ouput_shp)


    finally:
        # Suppression des couches de données temporaires
        gc.CleanAllTempFiles()


def splitted_to_unsplitted(splitted_net, splitted_RID_field, pts_lyr, pts_ID_field, pts_RID_field, pts_dist_field, width_field, unsplitted_net, unsplitted_RID_field, unslitted_l_field, outpts):
    # Find correspondance between a splitted and an unsplitted network

    # Find a RID match using a spatial join

    match_RID_table = gc.CreateScratchName("match", data_type="ArcInfoTable", workspace="in_memory")
    fms = arcpy.FieldMappings()
    # dans un premier temps j'ajoute le champ d'identification des iunités spatiales
    fmID = arcpy.FieldMap()
    fmID.addInputField(splitted_net, splitted_RID_field)
    type_name = fmID.outputField
    type_name.name = 'RID_A'
    fmID.outputField = type_name
    fms.addFieldMap(fmID)
    fmID_B = arcpy.FieldMap()
    fmID_B.addInputField(unsplitted_net, unsplitted_RID_field)
    type_name_B = fmID_B.outputField
    type_name_B.name = 'RID_B'
    fmID_B.outputField = type_name_B
    fms.addFieldMap(fmID_B)
    arcpy.SpatialJoin_analysis(splitted_net, unsplitted_net, match_RID_table, match_option="WITHIN", field_mapping=fms)

    # Then correct the distances, in points, using the distance of the "START" point of the splitted reach
    #  Find the start points
    start_pts = gc.CreateScratchName("pts", data_type="FeatureClass", workspace="in_memory")
    arcpy.FeatureVerticesToPoints_management(splitted_net, start_pts, "START")
    #  Join to have the unsplitted RID
    arcpy.MakeFeatureLayer_management(start_pts, "start_lyr")
    arcpy.AddJoin_management("start_lyr", splitted_RID_field, match_RID_table, "RID_A")
    #  Project start points on the right unsplitted reach
    splits_along = gc.CreateScratchName("split", data_type="ArcInfoTable", workspace="in_memory")
    execute_LocatePointsAlongRoutes("start_lyr", arcpy.Describe(match_RID_table).basename + ".RID_B", unsplitted_net, unsplitted_RID_field, splits_along, 1)
    #  Join the result to the data points
    arcpy.AddJoin_management(pts_lyr, pts_RID_field, splits_along, "RID_A")
    #  Join the river network to get the max possible length (needed to fix issues where the measured distance is slightly over the reach length
    arcpy.AddJoin_management(pts_lyr, arcpy.Describe(splits_along).basename+".RID_B", unsplitted_net, unsplitted_RID_field)

    #  Correct distances
    result_np = arcpy.da.TableToNumPyArray(pts_lyr, [arcpy.Describe(pts_lyr).basename+"."+pts_ID_field, arcpy.Describe(pts_lyr).basename+"."+width_field,
                                                     arcpy.Describe(pts_lyr).basename+"."+pts_dist_field, arcpy.Describe(splits_along).basename+".RID_B",
                                                     arcpy.Describe(splits_along).basename+".MEAS", arcpy.Describe(unsplitted_net).basename+"."+unslitted_l_field])
    result_np.dtype.names = [pts_ID_field, width_field, pts_dist_field, pts_RID_field, "MEAS", "Max_l"]
    result_np[pts_dist_field] = result_np[pts_dist_field] + result_np["MEAS"]
    result_np[pts_dist_field] = np.minimum(result_np[pts_dist_field], result_np["Max_l"])
    arcpy.da.NumPyArrayToTable(result_np[[pts_ID_field, width_field, pts_dist_field, pts_RID_field]], outpts)