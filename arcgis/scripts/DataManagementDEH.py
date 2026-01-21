# -*- coding: utf-8 -*-

# ******************************************************************************
# Auteur: François Larouche-Tremblay, Ing, M Sc
# Date: 27/05/2021
# Description: Fonctions et classes qui servent à la gestion des matrices et
# des couches de données temporaires.
# ******************************************************************************
import arcpy
import numpy as np
from os.path import normpath, join
from arcpy import env, CreateScratchName
from arcpy.management import Delete, DeleteField


def addfieldtoarray(inarr, *fields):
    # **************************************************************************
    # DÉFINITION :
    # Ajoute un ou des champs à une "structured array"
    # ENTRÉES :
    # inarr: structured array
    # fields: name ou (name, dtype)

    # SORTIE :
    # outarr: structured array avec des champs supplémentaires
    # **************************************************************************
    old_fields = inarr.dtype.descr
    if len(old_fields) > len(inarr.dtype.fields):  # Si la matrice est une "view", elle a un champ bidon de plus?
        old_fields = old_fields[:-1]

    for field in fields:
        if isinstance(field, str):
            old_fields.append((field, np.float32))
        elif isinstance(field, tuple):
            old_fields.append(field)

    new_dtype = np.dtype(old_fields)
    outarr = np.empty(inarr.shape, dtype=new_dtype)
    for name in inarr.dtype.names:
        outarr[name] = inarr[name]

    return outarr


class Dataset(object):
    # **************************************************************************
    # DÉFINITION :
    # Chemin d'accès vers un jeu de données ArcGIS. (directory : string)
    # (data_type : String) Peut avoir un identifiant de catégorie. (memslot : int)
    # **************************************************************************

    def __init__(self, directory, data_type, memslot=0):
        self.directory = directory
        self.datatype = data_type
        self.memslot = memslot


class ScratchIndex(object):
    # **************************************************************************
    # DÉFINITION :
    # Index pour la gestion et la suppression des couches de
    # données temporaires. Tous les types de données ArcGIS sont pris en charge
    # (Exemple: "FeatureClass", "RasterDataset"), en plus du type maison "Table".
    # **************************************************************************
    def __init__(self, dirlist=None):
        if dirlist is None:
            dirlist = []

        self.dirlist = dirlist
        self.filecount = len(self.dirlist)
        self.tablecount = 0
        for dataset in dirlist:
            if dataset.datatype == "Table":
                self.tablecount += 1

    def scratchname(self, prefix, data_type, workspace="memory", memslot=99):
        # **************************************************************************
        # DÉFINITION :
        # Permet de générer des noms de données temporaires avec
        # un préfix (prefix : String) et un numéro unique, ayant le bon format
        # selon le type de données. (data_type : String) Si le workspace n'est
        # pas spécifié, la donnée sera enregistrée en mémoire. Le jeu de donnée
        # peut être associé à une catégorie.
        # **************************************************************************

        if data_type == "Table":
            workspace = env.scratchWorkspace  # Les tables ne peuvent être créées en mémoire
            tablename = "t{0}{1:02d}".format(prefix, self.tablecount)
            name = normpath(join(workspace, tablename))
            self.tablecount += 1
        else:
            name = CreateScratchName(prefix, data_type=data_type, workspace=workspace)

        self.dirlist.append(Dataset(name, data_type, memslot))
        self.filecount = len(self.dirlist)

        return name

    def addtoscratch(self, directory, data_type, memslot=0):
        # **************************************************************************
        # DÉFINITION :
        # Permet d'ajouter un jeu de données déjà existant
        # (directory : string) (data_type : String) à la liste des couches
        # temporaires et de l'associer à une catégorie. (memslot : int)
        # **************************************************************************

        self.dirlist.append(Dataset(directory, data_type, memslot))
        self.filecount = len(self.dirlist)
        if data_type == "Table":
            self.tablecount += 1

        return

    def wipeindex(self, memslot=None):
        # **************************************************************************
        # DÉFINITION :
        # Permet d'effacer tous les jeux de données temporaires
        # ou seulement ceux de certaines catégories. (memslot : int)
        # **************************************************************************

        if memslot is None:
            garbagebin = [ds.directory for ds in self.dirlist]
            self.dirlist = []
            self.filecount = len(self.dirlist)
            self.tablecount = 0
        else:
            newdirlist = [ds for ds in self.dirlist if ds.memslot != memslot]
            garbagebin = [ds.directory for ds in self.dirlist if ds.memslot == memslot]
            self.dirlist = newdirlist
            self.filecount = len(self.dirlist)
            self.tablecount = 0
            for dataset in self.dirlist:
                if dataset.datatype == "Table":
                    self.tablecount += 1

        for directory in garbagebin:
            Delete(directory)


def deleteuselessfields(feature, keepers, mapping="FC"):
    # **************************************************************************
    # DÉFINITION :
    # Supprime tous les champs de la table qui ne sont pas listés dans keepers.

    # ENTRÉES :
    # feature = chemin d'accès vers la table ou la feature class, ou objet FieldMappings
    # keepers = Liste de noms de champs à conserver
    # mapping = STRING, indique si l'objet à modifier est la table d'attribut
    # de la feature class (FC) ou un FieldMappings (FMS)

    # SORTIE :
    # Les champs inutiles de la feature originale sont supprimés.
    # **************************************************************************
    fieldnames = [kp.upper() for kp in keepers]
    if mapping == "FMS":
        for field in feature.fields:
            fname = field.name
            if fname.upper() not in fieldnames:  # On conserve seulement les champs désirés
                feature.removeFieldMap(feature.findFieldMapIndex(fname))

        return feature

    for field in arcpy.ListFields(feature):
        fname = field.name
        if fname.upper() not in fieldnames:
            DeleteField(feature, fname)
    return


def getfieldproperty(feature, fieldname, prop, default=None):
    # **************************************************************************
    # DÉFINITION :
    # Effectue une requête pour extraire les propriétés et les champs demandés.

    # ENTRÉES :
    # feature = chemin d'accès vers la table ou la feature class
    # fieldname = nom de champ
    # prop = STRING, propriété à extraire
    # field.property : type, editable, required, scale, precision
    # SORTIE :
    # Les propriétés demandées
    # **************************************************************************
    for field in arcpy.ListFields(feature):
        fname = field.name
        if fname == fieldname:
            fieldattr = getattr(field, prop)
            if prop == "type":
                fieldattr = fieldattr.upper()

            return fieldattr

    return default
