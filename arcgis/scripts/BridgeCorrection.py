# coding: latin-1

#####################################################
# Guénolé Choné
# Concordia University
# Geography, Planning and Environment Department
# guenole.chone@concordia.ca
#####################################################

# Versions
# v1.0 - Mai 2020 - Création. Code déplacé des fichier Interface. Procédure changé avec ajout d'un fill, plutôt que le
#        min pour chaque pont (possibles valeurs trop basses sinon)
# v1.1 - Septembre 2020 - Modification pour inclure systématiquement tout pixel touché par les polygones


import arcpy
from RasterIO import *

def execute_BridgeCorrection(r_dem, str_bridges, str_result, messages, language = "FR"):


    with arcpy.EnvManager(snapRaster=r_dem):
        with arcpy.EnvManager(extent=r_dem):

            linebridges = arcpy.CreateScratchName("lines", data_type="FeatureClass", workspace=arcpy.env.scratchWorkspace)
            arcpy.PolygonToLine_management(str_bridges, linebridges, "IGNORE_NEIGHBORS")

            r_linebridges = arcpy.CreateScratchName("rlines", data_type="RasterDataset", workspace=arcpy.env.scratchWorkspace)
            arcpy.PolylineToRaster_conversion(linebridges, "ORIG_FID", r_linebridges, cellsize=r_dem)

            r_polybridges = arcpy.CreateScratchName("rpoly", data_type="RasterDataset", workspace=arcpy.env.scratchWorkspace)
            arcpy.PolygonToRaster_conversion(str_bridges, arcpy.Describe(str_bridges).OIDFieldName, r_polybridges, cellsize=r_dem)

            r_bridges = arcpy.sa.Con(arcpy.sa.IsNull(r_polybridges)==1, r_linebridges, r_polybridges)

            z_bridges = arcpy.sa.ZonalStatistics(r_bridges, "VALUE", r_dem, "MINIMUM")

            temp_isnull = arcpy.sa.IsNull(z_bridges)

            temp_dem = arcpy.sa.Con(temp_isnull, z_bridges, r_dem, "VALUE = 0")
            temp_fill = arcpy.sa.Fill(temp_dem)
            result = arcpy.sa.Con(temp_isnull, temp_fill, r_dem, "VALUE = 0")
            result.save(str_result)

            arcpy.Delete_management(linebridges)
            arcpy.Delete_management(r_linebridges)