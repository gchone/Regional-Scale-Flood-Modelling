
import LASfileTimeExtractor
import time

start_time = time.time()
input_laz_folder = r"D:\NRCAN2\FloodToolsOpenGIS\Test_LAS_GR\Laz_files"
bydays_folder = r"D:\NRCAN2\FloodToolsOpenGIS\Test_LAS_GR\bydays"
ground_folder = r"D:\NRCAN2\FloodToolsOpenGIS\Test_LAS_GR\ground"
merged_folder = r"D:\NRCAN2\FloodToolsOpenGIS\Test_LAS_GR\merged"
UTC = -4

# First tool: Filter las or laz files by days of LiDAR acquisition
LASfileTimeExtractor.execute_extract_bydays(input_laz_folder, UTC, bydays_folder)
# Second tool: Ground points classification and filtering
LASfileTimeExtractor.execute_groundclassification(bydays_folder, ground_folder)
# Third tool: Merging together tiles of same day of LiDAR acquisition
LASfileTimeExtractor.execute_mergelas(ground_folder, merged_folder)

# Fourth tool: Las to raster conversion
output_folder = r"D:\NRCAN2\FloodToolsOpenGIS\Test_LAS_GR\rasters"
LASfileTimeExtractor.execute_lastoraster(merged_folder, output_folder, 1)

# Calculate the elapsed time
end_time = time.time()
elapsed_time = end_time - start_time
print(f"Execution time: {elapsed_time:.2f} seconds")
