# coding: latin-1

#####################################################
# Guénolé Choné
# Concordia University
# Geography, Planning and Environment Department
# guenole.chone@concordia.ca
#####################################################

# Versions
# v2.0 - Février 2019 - Création
# v2.1 - Septembre 1019 - Code ré-écrit pour plus de clarté
# v2.2 - Mai 2020 -  Ménage pour ajout dans le package FloodTools. Prise en charge d'arbres multiples. Fonction et fichier renommé

import os
import arcpy
import random
from RasterIO import *
from tree_rasters.OurTreeSegment import *
from tree_rasters.OurTreeManager import *




def execute_SpatializeQ(r_flowdir, str_frompoint, r_flowacc, r_qpts, str_res, interpolation):


    flowdir = RasterIO(r_flowdir)
    flowacc = RasterIO(r_flowacc)
    qpts = RasterIO(r_qpts)

    Res = RasterIO(r_flowdir, str_res, float, flowacc.nodata)
    trees = build_trees(flowdir,str_frompoint,Q=qpts,flowacc=flowacc)


    for tree in trees:
        # transmitting from upstream point
        for segment, prev_cs, cs in tree.uptodown_browsepts():
            cs.A = float(cs.flowacc)
            if cs.Q != qpts.nodata and cs.Q != 0: ## cs.Q != 0 ajouté à cause d'un problème de NoData. Pas propre.
                cs.up_ptsA = cs.A
                cs.up_ptsQ = cs.Q
            elif prev_cs is not None:
                cs.up_ptsA = prev_cs.up_ptsA
                cs.up_ptsQ = prev_cs.up_ptsQ
            else:
                cs.up_ptsA = 0
                cs.up_ptsQ = 0

        # transmitting from downstream point
        for segment, prev_cs, cs in tree.browsepts():



            if cs.Q != qpts.nodata and cs.Q != 0: ## cs.Q != 0 ajouté à cause d'un problème de NoData. Pas propre.
                cs.down_ptsA = cs.A
                cs.down_ptsQ = cs.Q

            else:
                if prev_cs is not None:
                    cs.down_ptsA = prev_cs.down_ptsA
                    cs.down_ptsQ = prev_cs.down_ptsQ
                else:
                    cs.down_ptsA = 0
                    cs.down_ptsQ = 0


                if interpolation:
                    cs.alpha = (cs.up_ptsQ - cs.down_ptsQ) / (cs.up_ptsA - cs.down_ptsA)
                    cs.beta = cs.down_ptsQ - cs.alpha * cs.down_ptsA
                    cs.Q = cs.alpha * cs.A + cs.beta
                    print(cs.Q)
                else:
                    if cs.down_ptsA == 0:
                        # cas particulier : pas d'interpolation (débit de crue), et extrapolation down
                        cs.Q = cs.up_ptsQ/cs.up_ptsA*cs.A
                    else:
                        cs.Q = cs.down_ptsQ/cs.down_ptsA*cs.A




        for segment in tree.treesegments():
            for pt in segment.get_profile():
                Res.setValue(pt.row, pt.col, pt.Q)

    Res.save()


    return



