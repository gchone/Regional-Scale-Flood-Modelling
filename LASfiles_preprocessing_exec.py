import LASfiles_preprocessing
import time

start_time = time.time()

UTC = -4
input_laz_folder = r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\origlas_2018_05_02"
bydays_folder = r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\byday_2018_05_02"
# First tool: Filter las or laz files by days of LiDAR acquisition
#LASfiles_preprocessing.execute_extract_bydays(input_laz_folder, UTC, bydays_folder)

ground_folder = r"D:\NRCAN2\temp\New folder\new_ground"
str_binlastoolsfolder = r"D:\lastools\LAStools\bin"
# Second tool: Ground points classification and filtering
#LASfiles_preprocessing.execute_groundclassification(str_binlastoolsfolder, bydays_folder, ground_folder)

## For Ontario dataset: converting LAS files to raster by tile before merging the tiles by day of LiDAR aquisition ##
## Note that LASfiles_preprocessing.execute_convertbytile rely on the naming convention of the Ontario dataset to find
## the position of the tiles in the UTM17 coordinate system. This script needs to be adapted in order for it to work
## for other datasets. ##
output_folder = r"D:\NRCAN2\temp\New folder\new_dems"
ref_raster = r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\lasground_1km175470483702018LLAKEERIE.tif"
# Third tool: Convert LAS files to raster by tile
#LASfiles_preprocessing.execute_convertbytile(ground_folder, output_folder, ref_raster, 1)

# Fourth tool: Merge rasters (by tiles) into a single raster for each day of LiDAR acquisition
#   not implemented in Python. Can be done with ArcGIS Pro or QGIS.


## For smaller dataset than the Ontario one: merging LAS files by day and converting to raster ##
# Third tool: Merging together tiles of same day of LiDAR acquisition
#LASfiles_preprocessing.execute_mergelas(ground_folder, merged_folder)
# Fourth tool: Las to raster conversion
footprints = r"Z:\Projects\NRCan-LargeScaleFloodModeling\Phase2\Pilot_watersheds\Ontario\LASprocessing\footprints_fulltiles"
merged_folder = r"D:\NRCAN2\FloodToolsOpenGIS\TraitementLAS_ComputeCanada\ground_only"
output_folder = r"D:\NRCAN2\FloodToolsOpenGIS\TraitementLAS_ComputeCanada\rasters"
LASfiles_preprocessing.execute_lastoraster(merged_folder, output_folder, footprints, 1)

# Calculate the elapsed time
end_time = time.time()
elapsed_time = end_time - start_time
print(f"Execution time: {elapsed_time:.2f} seconds")


# python
import os
import argparse
import arcpy

arcpy.env.overwriteOutput = True

def create_shapefiles_for_folders(source_shapefile, input_root, output_root):
    ### Create the footprint shapefiles for each day, using the square tiles shapefile as source

    if not arcpy.Exists(source_shapefile):
        raise FileNotFoundError(f"Source shapefile ` {source_shapefile} ` not found.")
    # ensure field exists
    fields = [f.name for f in arcpy.ListFields(source_shapefile)]
    if 'FileName' not in fields:
        raise ValueError("Source shapefile must have a `FileName` field.")

    # Build mapping: lowercased FileName -> list of geometries
    mapping = {}
    with arcpy.da.SearchCursor(source_shapefile, ['FileName', 'SHAPE@']) as cur:
        for fname, geom in cur:
            if fname is None:
                continue
            key = fname.lower()
            mapping.setdefault(key, []).append(geom)

    src_sr = arcpy.Describe(source_shapefile).spatialReference

    # Walk input_root and process each .las
    for dirpath, dirnames, filenames in os.walk(input_root):
        lasfiles = [f for f in filenames if f.lower().endswith('.las')]
        if not lasfiles:
            continue




        # Collect all geometries and file names for this folder
        records = []
        for las in lasfiles:
            base = os.path.splitext(las)[0]
            target = base.lower() + '.laz'
            geoms = mapping.get(target)
            if not geoms:
                print(f"Skipping ` {os.path.join(dirpath, las)} ` — no matching polygons for ` {target} `.")
                continue
            # Union geometries for this LAS file
            union_geom = geoms[0]
            for g in geoms[1:]:
                union_geom = union_geom.union(g)
            records.append((las, union_geom))

        # Create a single shapefile for all LAS files in this folder
        rel = os.path.relpath(dirpath, input_root)
        out_name = "footprint_" + rel + ".shp"
        out_fc = os.path.join(output_root, out_name)
        if arcpy.Exists(out_fc):
            arcpy.Delete_management(out_fc)
        arcpy.CreateFeatureclass_management(output_root, out_name, "POLYGON", spatial_reference=src_sr)
        arcpy.AddField_management(out_fc, "FileName", "TEXT", field_length=254)

        # Insert all records
        with arcpy.da.InsertCursor(out_fc, ['FileName', 'SHAPE@']) as icur:
            for fname, geom in records:
                icur.insertRow([fname, geom])
        print(f"Wrote `{out_fc}` with {len(records)} features.")

# if __name__ == '__main__':
#     source_shapefile = r"D:\NRCAN2\GrandRiver\laz_grid.shp"
#     input_root = r"Z:\Projects\NRCan-LargeScaleFloodModeling\Phase2\Pilot_watersheds\Ontario\LASprocessing\ground-by-day2"
#     output_root = r"Z:\Projects\NRCan-LargeScaleFloodModeling\Phase2\Pilot_watersheds\Ontario\LASprocessing\footprints_fulltiles"
#
#     create_shapefiles_for_folders(source_shapefile,input_root, output_root)