import math

import laspy.lib
import numpy as np
import os
from datetime import datetime, timedelta
import json
import subprocess
import scipy.interpolate
from osgeo import gdal
gdal.UseExceptions()

def gps_week_to_datetime(gps_time, gps_week_start):
    return gps_week_start + timedelta(seconds=gps_time)

def execute_extract_bydays(str_lasfolder, UTC, output_folder):

    day_vec = np.vectorize(lambda t: t.date())
    las_files = [f for f in os.listdir(str_lasfolder) if (f.endswith(".las") or f.endswith(".laz"))]
    for file in las_files:
        with laspy.open(os.path.join(str_lasfolder,file)) as laspyfile:
            # Read the point data
            las = laspyfile.read()

            # Ensure GPS time is available
            if 'gps_time' not in las.point_format.dimension_names:
                raise ValueError("GPS time is not available in the LAS file " + os.path.join(str_lasfolder,file))

            # Convert GPS time to datetime
            gps_times = las.gps_time
            gps_times = gps_times + int(1000000000) + int(UTC)*3600
            gps_week_start = datetime(1980, 1, 6)  # GPS epoch start

            gps_week_to_datetime_vec = np.vectorize(lambda t: gps_week_to_datetime(t, gps_week_start))
            datetimes = gps_week_to_datetime_vec(gps_times)

            # Extract unique days
            unique_days = np.unique(day_vec(datetimes))


            # Split and save LAS files by day
            for day in unique_days:
                mask = np.array([dt.date() == day for dt in datetimes])
                sub_las = laspy.create(point_format=las.header.point_format, file_version=las.header.version)
                sub_las.points = las.points[mask]
                output_filename = os.path.join(output_folder, str(day), file)
                if not os.path.exists(os.path.join(output_folder, str(day))):
                    os.makedirs(os.path.join(output_folder, str(day)))
                sub_las.write(output_filename)
                print(f"Saved {output_filename} with {mask.sum()} points.")

                ### PDAL solution. Slower ###
                # # Define GPS time range (modify these values)
                # gps_time_min = (datetime.combine(day, datetime.min.time()) - gps_week_start).total_seconds() - int(UTC)*3600 - int(1000000000)
                # gps_time_max = gps_time_min + 24*60*60
                #
                # # Define PDAL pipeline
                # pipeline = {
                #     "pipeline": [
                #         os.path.join(r,file),
                #         {
                #             "type": "filters.range",
                #             "limits": f"GpsTime[{gps_time_min}:{gps_time_max}]"  # Filter based on GPS time range,
                #         },
                #         os.path.join(output_folder, str(day), file[:-4]+".las"),
                #     ]
                # }
                #
                # # Run PDAL pipeline
                # subprocess.run(["pdal", "pipeline", "--stdin"], input=json.dumps(pipeline), text=True)


def execute_groundclassification(input_folder, ground_folder):
    filelist = []
    outputlist = []
    for r, d, f in os.walk(input_folder):
        for file in f:
            if (file[-4:] == '.laz' or file[-4:] == '.las'):
                filelist.append(os.path.join(r, file))
                outputfolder = os.path.join(ground_folder, r[len(input_folder)+1:])
                outputlist.append(os.path.join(outputfolder, file[:-4]+".las"))
                if not os.path.exists(outputfolder):
                    os.makedirs(outputfolder)
                pipeline = {
                    "pipeline": [
                        os.path.join(r, file),
                        {
                            "type": "filters.smrf",  # Simple Morphological Filter for ground classification
                            #Example parameters:
                            # "scalar": 1.2,
                            # "slope": 0.2,
                            # "window": 33,
                            # "threshold": 0.45
                        },
                        {
                            "type": "filters.range",
                            "limits": "Classification[2:2]"
                        },
                        os.path.join(outputfolder, file[:-4]+".las")
                    ]
                }
                # Run PDAL pipeline
                subprocess.run(["pdal", "pipeline", "--stdin"], input=json.dumps(pipeline), text=True)

def execute_mergelas(input_folder, output_folder):

    daydict = {} # Let's create a dictionnary with the day of lidar acquisition as key and list of las files
    for r, d, f in os.walk(input_folder):
        for file in f:
            if (file[-4:] == '.laz' or file[-4:] == '.las'):
                day = r[len(input_folder)+1:]
                if day not in daydict.keys():
                    daydict[day] = []
                daydict[day].append(os.path.join(r, file))

    for day, laslist in daydict.items():
        pipeline = laslist.copy()
        pipeline.append({
                    "type": "writers.las",
                    "filename": os.path.join(output_folder, day+".las")
                })
        pipeline = {"pipeline": pipeline}
        # Run PDAL pipeline
        subprocess.run(["pdal", "pipeline", "--stdin"], input=json.dumps(pipeline), text=True)

def execute_lastoraster(input_folder, output_folder, cellsize):
    # List all LAS files in the input folder
    las_files = [f for f in os.listdir(input_folder) if f.endswith(".las")]

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    snap_ref_x = None
    snap_ref_y = None
    # Process each LAS file
    for file in las_files:
        full_path_input_file = os.path.join(input_folder, file)
        with laspy.open(full_path_input_file) as las:
            # Get the minimum x and y values
            min_x, min_y, min_z = las.header.mins
            max_x, max_y, max_z = las.header.maxs
            if snap_ref_x is None:
                # If this is the first file, set the reference point to the min coordinates
                snap_ref_x = min_x
                snap_ref_y = min_y
            else:
                # Snap the min coordinates values to the reference point
                min_x = snap_ref_x - math.ceil((snap_ref_x - min_x) / cellsize)*cellsize
                min_y = snap_ref_y - math.ceil((snap_ref_y - min_y) / cellsize)*cellsize

        output_rasterfile = os.path.join(output_folder, file[:-4] + ".tif")

        # Define the PDAL pipeline
        pipeline = {
            "pipeline": [
                {
                    "type": "readers.las",
                    "filename": full_path_input_file
                },
                {
                    "type": "filters.delaunay"  # Create a TIN from the LAS points
                },
                {
                    "type": "filters.faceraster",  # Interpolate the TIN to create a raster
                    "resolution": cellsize,  # Set the raster resolution (cell size)
                    "origin_x": min_x,  # Set the origin of the raster
                    "origin_y": min_y,
                    "width": math.ceil((max_x - min_x) / cellsize),  # Set the width of the raster
                    "height": math.ceil((max_y - min_y) / cellsize)  # Set the height of the raster
                },
                {
                    "type": "writers.raster",  # Save the raster as a GeoTIFF
                    "filename": output_rasterfile,
                    "gdaldriver": "GTiff",  # Use GeoTIFF format
                    "data_type": "Float32"  # Set the data type of the raster

                }
            ]
        }

        # Run the PDAL pipeline
        result = subprocess.run(["pdal", "pipeline", "--stdin"], input=json.dumps(pipeline), text=True, capture_output=True)
        print(result.stderr)

        # Fill voids using python-GDAL
        # That could also be done with cipy.interpolate.griddata. I haven't tried yet.
        driver = gdal.GetDriverByName('GTiff')
        filled_rasterfile = os.path.splitext(output_rasterfile)[0] + "_filled.tif"
        dataset = gdal.Open(output_rasterfile)
        filled_dataset = driver.CreateCopy(filled_rasterfile, dataset, 0)
        gdal.FillNodata(targetBand=filled_dataset.GetRasterBand(1), maskBand=None,
                                 maxSearchDist=1000, smoothingIterations=0)
        print(filled_rasterfile + " created")

    return