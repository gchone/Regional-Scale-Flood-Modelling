
import LASfiles_preprocessing
import time

start_time = time.time()

UTC = -4
input_laz_folder = r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\origlas_2018_05_02"
bydays_folder = r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\byday_2018_05_02"
# First tool: Filter las or laz files by days of LiDAR acquisition
#LASfiles_preprocessing.execute_extract_bydays(input_laz_folder, UTC, bydays_folder)

bydays_folder = r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\byday_for2018_05_02\2018-05-02"
ground_folder = r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\lastools_class2only"
str_binlastoolsfolder = r"D:\lastools\LAStools\bin"
# Second tool: Ground points classification and filtering
#LASfiles_preprocessing.execute_groundclassification(str_binlastoolsfolder, bydays_folder, ground_folder)

## For Ontario dataset: converting LAS files to raster by tile before merging the tiles by day of LiDAR aquisition ##
## Note that LASfiles_preprocessing.execute_convertbytile rely on the naming convention of the Ontario dataset to find
## the position of the tiles in the UTM17 coordinate system. This script needs to be adapted in order for it to work
## for other datasets. ##
output_folder = r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\rasters_2018_05_02"
ref_raster = R"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\lasground_1km175470483702018LLAKEERIE.tif"
# Third tool: Convert LAS files to raster by tile
LASfiles_preprocessing.execute_convertbytile(ground_folder, output_folder, ref_raster, 1)

# Fourth tool: Merge rasters (by tiles) into a single raster for each day of LiDAR acquisition
#   not implemented in Python. Can be done with ArcGIS Pro or QGIS.


## For smaller dataset than the Ontario one: merging LAS files by day and converting to raster ##
# Third tool: Merging together tiles of same day of LiDAR acquisition
#LASfiles_preprocessing.execute_mergelas(ground_folder, merged_folder)
# Fourth tool: Las to raster conversion
#LASfiles_preprocessing.execute_lastoraster(merged_folder, output_folder, 1)

# Calculate the elapsed time
end_time = time.time()
elapsed_time = end_time - start_time
print(f"Execution time: {elapsed_time:.2f} seconds")
