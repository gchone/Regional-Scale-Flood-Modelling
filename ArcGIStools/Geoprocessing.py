from pathlib import Path
import sys

import arcpy
import os
import uuid

_LEGACY_ARCGIS_DIR = Path(__file__).resolve().parents[1] / "Regional-Scale-Flood-Modelling-ArcGIS"
if str(_LEGACY_ARCGIS_DIR) not in sys.path:
    sys.path.append(str(_LEGACY_ARCGIS_DIR))

import numpy as np
from os.path import basename
from arcpy.lr import MakeRouteEventLayer
from arcpy.management import AddField, CalculateField, SelectLayerByLocation, MakeFeatureLayer, \
    DeleteIdentical, FeatureVerticesToPoints, JoinField, AlterField, SplitLineAtPoint, CopyFeatures, \
    SelectLayerByAttribute, MultipartToSinglepart, DeleteRows, DeleteField, Merge, PolygonToLine, \
    CreateTable, PointsToLine
from arcpy.analysis import Intersect, Buffer, Statistics, Erase, Near, SpatialJoin
from arcpy.da import NumPyArrayToTable, TableToNumPyArray, FeatureClassToNumPyArray
from .DataManagementDEH import addfieldtoarray, deleteuselessfields, getfieldproperty
from . import ArcpyGarbageCollector as gc

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

# Create a buffer around a shape
def buffer(input_shapefile, output_shapefile, buffer_distance):
    arcpy.Buffer_analysis(input_shapefile, output_shapefile, buffer_distance)

# Add other geoprocessing tools and procedures
# ...


def create_points_on_route_layer(routes, routes_id_field, points_onroute, points_onroute_ridfield, points_onroute_distfield):
    layer_name = f"assignpointonroute_{uuid.uuid4().hex}"
    arcpy.MakeRouteEventLayer_lr(
        routes,
        routes_id_field,
        points_onroute,
        points_onroute_ridfield + " POINT " + points_onroute_distfield,
        layer_name,
    )
    return layer_name


def delete_layer(layer_name):
    if arcpy.Exists(layer_name):
        arcpy.Delete_management(layer_name)


def rasterize_polygons_to_match(input_polygons, reference_raster, reference_grid, output_path):
    del reference_grid
    output_coordinate_system = getattr(reference_raster, "spatialReference", reference_raster)
    with arcpy.EnvManager(
        snapRaster=reference_raster,
        outputCoordinateSystem=output_coordinate_system,
        extent=reference_raster,
    ):
        if arcpy.Exists(output_path):
            arcpy.Delete_management(output_path)
        arcpy.PolygonToRaster_conversion(
            input_polygons,
            arcpy.Describe(input_polygons).OIDFieldName,
            output_path,
            cellsize=reference_raster,
        )
    return output_path


def rasterize_lines_to_match(input_lines, reference_raster, reference_grid, output_path):
    del reference_grid
    output_coordinate_system = getattr(reference_raster, "spatialReference", reference_raster)
    with arcpy.EnvManager(
        snapRaster=reference_raster,
        outputCoordinateSystem=output_coordinate_system,
        extent=reference_raster,
    ):
        if arcpy.Exists(output_path):
            arcpy.Delete_management(output_path)
        arcpy.PolylineToRaster_conversion(
            input_lines,
            arcpy.Describe(input_lines).OIDFieldName,
            output_path,
            cellsize=reference_raster,
        )
    return output_path


def point_to_raster_most_frequent(input_points, value_field, reference_raster, output_path):
    output_coordinate_system = getattr(reference_raster, "spatialReference", reference_raster)
    with arcpy.EnvManager(
        snapRaster=reference_raster,
        outputCoordinateSystem=output_coordinate_system,
        extent=reference_raster,
    ):
        delete_dataset(output_path)
        arcpy.PointToRaster_conversion(
            input_points,
            value_field,
            output_path,
            cell_assignment="MOST_FREQUENT",
            priority_field=None,
            cellsize=reference_raster,
        )
    return output_path


def burn_streams_into_dem(input_raster, polygon_raster, line_raster, output_path):
    delete_dataset(output_path)
    burned_frompoly = arcpy.sa.Con(arcpy.sa.IsNull(polygon_raster), input_raster, input_raster - 100)
    burned = arcpy.sa.Con(arcpy.sa.IsNull(line_raster), burned_frompoly, input_raster - 200)
    burned.save(output_path)
    return output_path


def build_tiling_buffer_extents(segments_raster, buffer_distance, output_folder):
    line_segments = os.path.join(output_folder, "line_segments.shp")
    buffered_segments = os.path.join(output_folder, "buff_segments.shp")

    scratch_workspace = arcpy.env.scratchWorkspace
    if scratch_workspace in [None, ""]:
        scratch_workspace = output_folder

    temp_segments = os.path.join(scratch_workspace, f"tmpsegments_{uuid.uuid4().hex}.shp")
    temp_segments_buffer = os.path.join(scratch_workspace, f"tmpsegments_buf_{uuid.uuid4().hex}.shp")
    temp_segments_merge = os.path.join(scratch_workspace, f"tmpsegments_merge_{uuid.uuid4().hex}.shp")
    temp_segments_polygon = os.path.join(scratch_workspace, f"tmpsegments_poly_{uuid.uuid4().hex}.shp")

    for dataset in [line_segments, buffered_segments, temp_segments, temp_segments_buffer, temp_segments_merge, temp_segments_polygon]:
        if arcpy.Exists(dataset):
            arcpy.Delete_management(dataset)

    arcpy.RasterToPolyline_conversion(segments_raster, temp_segments)
    arcpy.Dissolve_management(temp_segments, line_segments, "GRID_CODE")

    arcpy.Buffer_analysis(line_segments, temp_segments_buffer, float(buffer_distance) / 10.0)
    segments_allocation = arcpy.sa.EucAllocation(segments_raster, buffer_distance)
    arcpy.RasterToPolygon_conversion(segments_allocation, temp_segments_polygon)
    arcpy.AddField_management(temp_segments_polygon, "GRID_CODE", "LONG")
    arcpy.CalculateField_management(temp_segments_polygon, "GRID_CODE", "!GRIDCODE!", "PYTHON_9.3")

    arcpy.Merge_management([temp_segments_buffer, temp_segments_polygon], temp_segments_merge)
    arcpy.Dissolve_management(temp_segments_merge, buffered_segments, ["GRID_CODE"], multi_part="SINGLE_PART")

    records = []
    for grid_code, shape in arcpy.da.SearchCursor(buffered_segments, ["GRID_CODE", "SHAPE@"]):
        extent = shape.extent
        records.append({
            "GRID_CODE": int(grid_code),
            "XMin": float(extent.XMin),
            "YMin": float(extent.YMin),
            "XMax": float(extent.XMax),
            "YMax": float(extent.YMax),
        })

    for dataset in [temp_segments, temp_segments_buffer, temp_segments_merge, temp_segments_polygon]:
        if arcpy.Exists(dataset):
            arcpy.Delete_management(dataset)

    return {
        "line_segments": line_segments,
        "buffered_segments": buffered_segments,
        "records": records,
    }


def clip_raster_to_extent(input_raster, extent, output_path):
    if arcpy.Exists(output_path):
        arcpy.Delete_management(output_path)
    envelope = "{0} {1} {2} {3}".format(
        float(extent[0]),
        float(extent[1]),
        float(extent[2]),
        float(extent[3]),
    )
    arcpy.Clip_management(input_raster, envelope, output_path)
    return output_path


def clip_raster_to_template(input_raster, template_raster, output_path):
    if arcpy.Exists(output_path):
        arcpy.Delete_management(output_path)
    arcpy.Clip_management(input_raster, "#", output_path, template_raster, "#", "NONE", "MAINTAIN_EXTENT")
    return output_path


def raster_to_ascii(input_raster, output_path):
    if arcpy.Exists(output_path):
        arcpy.Delete_management(output_path)
    elif os.path.exists(output_path):
        os.remove(output_path)
    arcpy.RasterToASCII_conversion(input_raster, output_path)
    return output_path


def delete_dataset(path):
    if path in [None, ""]:
        return
    if arcpy.Exists(path):
        arcpy.Delete_management(path)
    elif os.path.exists(path):
        os.remove(path)


def rasterize_polygons_with_boundaries(input_polygons, reference_raster, reference_grid, output_path):
    del reference_grid
    scratch_workspace = arcpy.env.scratchWorkspace
    if scratch_workspace in [None, ""]:
        scratch_workspace = os.path.dirname(output_path)

    if str(scratch_workspace).lower().endswith(".gdb"):
        linebridges = os.path.join(scratch_workspace, f"bridge_lines_{uuid.uuid4().hex}")
    else:
        linebridges = os.path.join(scratch_workspace, f"bridge_lines_{uuid.uuid4().hex}.shp")
    r_linebridges = os.path.join(scratch_workspace, f"bridge_lines_{uuid.uuid4().hex}")
    r_polybridges = os.path.join(scratch_workspace, f"bridge_poly_{uuid.uuid4().hex}")

    output_coordinate_system = getattr(reference_raster, "spatialReference", reference_raster)
    try:
        with arcpy.EnvManager(
            snapRaster=reference_raster,
            outputCoordinateSystem=output_coordinate_system,
            extent=reference_raster,
        ):
            arcpy.PolygonToLine_management(input_polygons, linebridges, "IGNORE_NEIGHBORS")
            arcpy.PolylineToRaster_conversion(linebridges, "ORIG_FID", r_linebridges, cellsize=reference_raster)
            arcpy.PolygonToRaster_conversion(
                input_polygons,
                arcpy.Describe(input_polygons).OIDFieldName,
                r_polybridges,
                cellsize=reference_raster,
            )
            combined = arcpy.sa.Con(arcpy.sa.IsNull(r_polybridges) == 1, r_linebridges, r_polybridges)
            delete_dataset(output_path)
            combined.save(output_path)
    finally:
        for path in [linebridges, r_linebridges, r_polybridges]:
            delete_dataset(path)
    return output_path


def clip_raster_to_feature(input_raster, feature_class, feature_oid, output_path):
    layer_name = f"clip_feature_{uuid.uuid4().hex}"
    oid_field = arcpy.Describe(feature_class).OIDFieldName
    query = '"{0}" = {1}'.format(oid_field, int(feature_oid))
    try:
        arcpy.MakeFeatureLayer_management(feature_class, layer_name)
        arcpy.SelectLayerByAttribute_management(layer_name, "NEW_SELECTION", query)
        with arcpy.EnvManager(snapRaster=input_raster):
            clipped = arcpy.sa.ExtractByMask(input_raster, layer_name)
            delete_dataset(output_path)
            clipped.save(output_path)
    finally:
        delete_dataset(layer_name)
    return output_path


def collect_intersection_start_points(routes_main, polygon_feature_class, polygon_oid):
    layer_name = f"footprint_{uuid.uuid4().hex}"
    inline = f"in_memory\\inline_{uuid.uuid4().hex}"
    outpts = f"in_memory\\outpts_{uuid.uuid4().hex}"
    oid_field = arcpy.Describe(polygon_feature_class).OIDFieldName
    query = '"{0}" = {1}'.format(oid_field, int(polygon_oid))
    try:
        arcpy.MakeFeatureLayer_management(polygon_feature_class, layer_name)
        arcpy.SelectLayerByAttribute_management(layer_name, "NEW_SELECTION", query)
        arcpy.Intersect_analysis([routes_main, layer_name], inline, output_type="LINE")
        arcpy.FeatureVerticesToPoints_management(inline, outpts, "START")
        return [{"x": float(xy[0]), "y": float(xy[1])} for (xy,) in arcpy.da.SearchCursor(outpts, ["SHAPE@XY"])]
    finally:
        for path in [layer_name, inline, outpts]:
            delete_dataset(path)


def fill_dem(input_raster, output_path):
    delete_dataset(output_path)
    arcpy.sa.Fill(input_raster).save(output_path)
    return output_path


def compute_flow_direction(input_raster, output_path):
    delete_dataset(output_path)
    arcpy.sa.FlowDirection(input_raster).save(output_path)
    return output_path


def compute_flow_accumulation(input_raster, output_path):
    delete_dataset(output_path)
    arcpy.sa.FlowAccumulation(input_raster).save(output_path)
    return output_path


def compute_width_by_cross_sections(streamnetwork, idfield, riverbed, ineffarea, maxwidth, spacing, transects, cspoints, messages=None):
    legacy_messages = getattr(messages, "manager", messages)
    return execute_largeurpartransect(
        streamnetwork,
        idfield,
        riverbed,
        ineffarea,
        maxwidth,
        spacing,
        transects,
        cspoints,
        legacy_messages,
    )


def locate_features_along_routes_records(points, routes, routes_id_field, search_distance, field_names=None):
    from . import DataManagement

    output_table = f"in_memory\\locate_{uuid.uuid4().hex}"
    try:
        arcpy.LocateFeaturesAlongRoutes_lr(
            points,
            routes,
            routes_id_field,
            search_distance,
            output_table,
            routes_id_field + " POINT MEAS",
        )
        selected_fields = list(field_names or [])
        for field_name in [routes_id_field, "MEAS"]:
            if field_name not in selected_fields:
                selected_fields.append(field_name)
        return DataManagement.read_table_dataset(output_table, selected_fields)
    finally:
        delete_dataset(output_table)


def join_polygon_field_to_points_records(points, polygons, polygon_field, field_names=None):
    from . import DataManagement

    output_fc = f"in_memory\\join_{uuid.uuid4().hex}"
    try:
        arcpy.analysis.SpatialJoin(
            points,
            polygons,
            output_fc,
            join_operation="JOIN_ONE_TO_ONE",
            join_type="KEEP_ALL",
            match_option="INTERSECT",
        )
        selected_fields = list(field_names or [])
        if polygon_field not in selected_fields:
            selected_fields.append(polygon_field)
        return DataManagement.read_point_dataset(output_fc, selected_fields)
    finally:
        delete_dataset(output_fc)


def snap_points_to_nearest_line(points, lines, field_names=None, tolerance=None):
    from . import DataManagement

    line_info = DataManagement.read_table_dataset(lines)
    selected_line_fields = list(field_names or line_info["field_names"])
    point_info = DataManagement.read_point_dataset_any(points)
    selected_fields = list(point_info.get("field_names", []))
    for field_name in selected_line_fields:
        if field_name not in selected_fields:
            selected_fields.append(field_name)

    output_fc = f"in_memory\\snap_{uuid.uuid4().hex}"
    try:
        spatial_join_kwargs = {
            "join_operation": "JOIN_ONE_TO_ONE",
            "join_type": "KEEP_COMMON" if tolerance not in [None, ""] else "KEEP_ALL",
            "match_option": "CLOSEST",
        }
        if tolerance not in [None, ""]:
            spatial_join_kwargs["search_radius"] = tolerance
        arcpy.analysis.SpatialJoin(
            points,
            lines,
            output_fc,
            **spatial_join_kwargs,
        )
        return DataManagement.read_point_dataset_any(output_fc, selected_fields)
    finally:
        delete_dataset(output_fc)


def sample_raster_at_points(points_records_or_dataset, raster, output_field_name):
    from . import DataManagement

    point_info = _coerce_point_info(points_records_or_dataset, DataManagement)
    point_info = _clone_point_info_without_field(point_info, output_field_name)
    if len(point_info["records"]) == 0:
        field_names = list(point_info.get("field_names", []))
        if output_field_name not in field_names:
            field_names.append(output_field_name)
        point_info["field_names"] = field_names
        return point_info

    temp_points = f"in_memory\\sample_{uuid.uuid4().hex}"
    try:
        DataManagement.write_bed_assessment_points(
            temp_points,
            point_info["records"],
            point_info,
            [],
            spatial_reference=point_info.get("spatial_reference"),
        )
        arcpy.sa.ExtractMultiValuesToPoints(temp_points, [[raster, output_field_name]])
        return DataManagement.read_point_dataset_any(temp_points)
    finally:
        delete_dataset(temp_points)


def _coerce_point_info(points_records_or_dataset, DataManagement):
    if isinstance(points_records_or_dataset, dict) and "records" in points_records_or_dataset:
        point_info = dict(points_records_or_dataset)
        point_info["records"] = [dict(row) for row in points_records_or_dataset.get("records", [])]
        point_info["field_names"] = list(points_records_or_dataset.get("field_names", []))
        point_info["field_definitions"] = dict(points_records_or_dataset.get("field_definitions", {}))
        return point_info

    reader = getattr(DataManagement, "read_point_dataset_any", None)
    if reader is None:
        return DataManagement.read_point_dataset(points_records_or_dataset)
    return reader(points_records_or_dataset)


def _clone_point_info_without_field(point_info, field_name):
    field_names = [name for name in point_info.get("field_names", []) if name != field_name]
    field_definitions = dict(point_info.get("field_definitions", {}))
    field_definitions.pop(field_name, None)
    records = []
    for row in point_info.get("records", []):
        new_row = dict(row)
        new_row.pop(field_name, None)
        records.append(new_row)

    cloned = dict(point_info)
    cloned["records"] = records
    cloned["field_names"] = field_names
    cloned["field_definitions"] = field_definitions
    return cloned
