# -*- coding: utf-8 -*-

#####################################################
# Guénolé Choné
# Concordia University
# Geography, Planning and Environment Department
# guenole.chone@concordia.ca
#####################################################

import arcpy
import os
import ArcpyGarbageCollector as gc

def execute_FlowDirForWS(routes_main, DEM3m_forws, DEMs_footprints, output_workspace, exit_dist, messages):

    arcpy.MakeFeatureLayer_management(DEMs_footprints, "footprints_lyr")
    with arcpy.EnvManager(snapRaster=DEM3m_forws):
        try:
            footprints_OID = arcpy.Describe(DEMs_footprints).OIDFieldName
            with arcpy.da.SearchCursor(DEMs_footprints, [footprints_OID]) as cursor:
                for row in cursor:

                    # Select the footprint and clip
                    query = '"{}" = {}'.format(footprints_OID, str(row[0]))
                    arcpy.SelectLayerByAttribute_management("footprints_lyr", "NEW_SELECTION", query)
                    dem = arcpy.sa.ExtractByMask(DEM3m_forws, "footprints_lyr")

                    # Create pixel-exact footprint
                    bin_raster = arcpy.sa.Con(arcpy.sa.IsNull(dem) == 0, 10000)
                    domain = gc.CreateScratchName("domain", data_type="FeatureClass", workspace="in_memory")
                    arcpy.RasterToPolygon_conversion(bin_raster, domain, simplify="NO_SIMPLIFY")

                    # Create wall around the raster
                    domain_fullbuf = gc.CreateScratchName("domainb", data_type="FeatureClass", workspace="in_memory")
                    arcpy.Buffer_analysis(domain, domain_fullbuf, 3)
                    walls = gc.CreateScratchName("walls", data_type="RasterDataset", workspace=arcpy.env.scratchWorkspace)

                    arcpy.PolygonToRaster_conversion(domain_fullbuf, "GRIDCODE", walls, cellsize=dem)

                    # Find out points
                    inline = gc.CreateScratchName("inline", data_type="FeatureClass", workspace="in_memory")
                    arcpy.Intersect_analysis([routes_main, "footprints_lyr"], inline, output_type="LINE")
                    outpts = gc.CreateScratchName("outpts", data_type="FeatureClass", workspace="in_memory")
                    arcpy.FeatureVerticesToPoints_management(inline, outpts, "START")

                    # Buffer and Convert the out point into a raster
                    outpts_buf = gc.CreateScratchName("outpts_buf", data_type="FeatureClass", workspace="in_memory")
                    arcpy.Buffer_analysis(outpts, outpts_buf, exit_dist)
                    out_rpts = gc.CreateScratchName("out_rpts", data_type="RasterDataset", workspace=arcpy.env.scratchWorkspace)
                    with arcpy.EnvManager(extent=walls):
                        arcpy.PolygonToRaster_conversion(outpts_buf, arcpy.Describe(outpts_buf).OIDFieldName, out_rpts, cellsize=dem)

                    # Create the walled DEM
                    with arcpy.EnvManager(extent=walls):
                        walled = arcpy.sa.Con(arcpy.sa.IsNull(dem), arcpy.sa.Con(arcpy.sa.IsNull(out_rpts), walls), dem)

                    # Fill and Flow Dir
                    fill = arcpy.sa.Fill(walled)
                    flowdir = arcpy.sa.FlowDirection(fill)

                    # Clip
                    clip_flowdir = arcpy.sa.ExtractByMask(flowdir, dem)
                    clip_flowdir.save(os.path.join(output_workspace, "dem"+str(row[0])))

                    messages.addMessage("Done DEM with footprint id "+str(row[0]))


        finally:
            gc.CleanAllTempFiles()
