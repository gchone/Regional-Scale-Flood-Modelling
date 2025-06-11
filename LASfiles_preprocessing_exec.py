
import LASfiles_preprocessing
import time

start_time = time.time()
input_laz_folder = r"D:\NRCAN2\FloodToolsOpenGIS\Test_LAS_GR\Laz_files"
bydays_folder = r"D:\NRCAN2\FloodToolsOpenGIS\Test_LAS_GR\bydays"
ground_folder = r"D:\NRCAN2\FloodToolsOpenGIS\Test_LAS_GR\ground"
merged_folder = r"D:\NRCAN2\FloodToolsOpenGIS\Test_LAS_GR\merged"
UTC = -4

input_laz_folder = r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\origlas"
bydays_folder = r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\byday"

input_laz_folder = r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\origlas_2018_05_02"
bydays_folder = r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\byday_for2018_05_02"
# First tool: Filter las or laz files by days of LiDAR acquisition
#LASfiles_preprocessing.execute_extract_bydays(input_laz_folder, UTC, bydays_folder)
# Second tool: Ground points classification and filtering
#LASfiles_preprocessing.execute_groundclassification(bydays_folder, ground_folder)
# Third tool: Merging together tiles of same day of LiDAR acquisition
#LASfiles_preprocessing.execute_mergelas(ground_folder, merged_folder)

ground_folder = r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario"
output_folder = r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario_testrasters"

ground_folder = r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\lastools_class2only"
output_folder = r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\lastools_dems"

#LASfiles_preprocessing.execute_mergeandconvert(ground_folder, output_folder, 1)

pipeline = {
                    "pipeline": [
                        r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\byday_for2018_05_02\2018-05-02\2018-05-02\1km175470483702018LLAKEERIE.laz",
                        {
                            "type": "filters.assign",
                            "value": "Classification = 0"
                        },
                        {
                            "type": "filters.elm"
                        },
                        {
                            "type": "filters.outlier"
                        },
                        {
                            "type": "filters.smrf",
                            "where":"!(Classification == 7)",
                            # "slope":0.15,
                            # "window": 18
                            # "threshold": 0.5,
                            # "scalar": 1.25,
                            # "cell": 1.0,
                            # "cut": 0.0
                        },
                        {
                            "type":"filters.expression",
                            "expression":"Classification == 2"
                        },
                        r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\test_smrf2.las"
    ]
                }
# Run PDAL pipeline

import subprocess, json
subprocess.run(["pdal", "pipeline", "--stdin"], input=json.dumps(pipeline), text=True)
print("LAS classification done")

pipeline = {"pipeline": [
                        r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\test_smrf2.las",
                        {
                        "type": "filters.delaunay"  # Create a TIN from the LAS points
                        },
                        {
                        "type": "filters.faceraster",  # Interpolate the TIN to create a raster
                        "resolution": 1
                        },
                        {
                        "type": "writers.raster",  # Save the raster as a GeoTIFF
                        "filename": r"D:\NRCAN2\FloodToolsOpenGIS\LAS_Ontario\test_smrf2_raster.tif",
                        "gdaldriver": "GTiff",  # Use GeoTIFF format
                        "data_type": "Float32"  # Set the data type of the raster
                         }
                        ]
                }
subprocess.run(["pdal", "pipeline", "--stdin"], input=json.dumps(pipeline), text=True)



# Fourth tool: Las to raster conversion
#LASfiles_preprocessing.execute_lastoraster(merged_folder, output_folder, 1)

# Calculate the elapsed time
end_time = time.time()
elapsed_time = end_time - start_time
print(f"Execution time: {elapsed_time:.2f} seconds")
