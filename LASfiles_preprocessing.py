import math

import laspy.lib
import numpy as np
import os
from datetime import datetime, timedelta
import json
import subprocess
import scipy.interpolate
from osgeo import gdal
import re
gdal.UseExceptions()

def gps_week_to_datetime(gps_time, gps_week_start):
    return gps_week_start + timedelta(seconds=gps_time)

def execute_extract_bydays(str_lasfolder, UTC, output_folder):
    # This function extracts LAS files by days of LiDAR acquisition based on GPS time.
    # It creates a folder structure with the day as the folder name and saves the LAS files accordingly.
    # @param str_lasfolder: Path to the folder containing LAS files.
    # @param UTC: UTC offset in hours (e.g., -4 for Eastern Daylight Time).
    # @param output_folder: Path to the folder where the output files will be saved.

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Vectorize the date extraction for efficiency
    import numpy as np
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


def execute_groundclassification(str_binlastoolsfolder, input_folder, ground_folder):
    # This function classifies ground points in LAS files using LAStools' lasground_new64.exe.
    # Keeps only ground points (class 2) and saves them in a new folder structure.
    # @param str_binlastoolsfolder: Path to the folder containing the LAStools binaries.
    # @param input_folder: Path to the folder containing the input LAS files (= output of execute_extract_bydays).
    # @param ground_folder: Path to the folder where the ground classified LAS files will be saved.

    if not os.path.exists(ground_folder):
        os.makedirs(ground_folder)

    folders = [f for f in os.listdir(input_folder) if os.path.isdir(os.path.join(input_folder, f))]
    for folder in folders:
        outputfolder = os.path.join(ground_folder, folder)
        if not os.path.exists(outputfolder):
            os.makedirs(outputfolder)

        p = subprocess.Popen(
            [str_binlastoolsfolder + "\\lasground_new64.exe", "-demo", "-i", os.path.join(input_folder, folder, "*.la?"), "-odir",
             outputfolder, "-keep_class", "2"], cwd=input_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        out, err = p.communicate()  # make the script wait for the lasground to be done

def execute_convertbytile(input_folder, output_folder, ref_raster, cellsize = None):
    # Convert LAS files into DEMs with preliminary merging of the neighboring tiles.
    # This function was written for the Ontario LiDAR dataset, which has a specific naming convention for the LAS files.
    # It would need to be adapted for other datasets with different naming conventions.
    # @param input_folder: Path to the folder containing the input LAS files (= output of execute_groundclassification).
    # @param output_folder: Path to the folder where the output rasters will be saved.
    # @param ref_raster: Path to the reference raster file used for snapping the output rasters.
    # @param cellsize: Resolution of the output rasters. If None, it will be taken from the reference raster.
    #   Note that this function requires the cell size of the reference raster to be the same on the X and Y axes.

    # ref_raster is used to determine the cell size and the reference point for snapping.
    refdataset = gdal.Open(ref_raster)
    if not refdataset:
        raise FileNotFoundError(f"Unable to open raster file: {ref_raster}")
    # Get the geotransform
    geotransform = refdataset.GetGeoTransform()
    if not geotransform:
        raise ValueError("Geotransform is not available for the raster file.")
    # Extract minimum x, minimum y, and cell size
    snap_ref_x = geotransform[0]  # Top-left x coordinate
    snap_ref_y = geotransform[3]  # Top-left y coordinate
    if cellsize is None:
        cell_size_x = geotransform[1]  # Pixel width
        cell_size_y = abs(geotransform[5])  # Pixel height (absolute value)
        if cell_size_x != cell_size_y:
            raise ValueError("The reference raster must have the same cell size on both X and Y axes.")
        cellsize = (cell_size_x + cell_size_y) / 2  # Average cell size

    def parse_filename_ON(filename):
        """
        Parse the filename to extract UTM17 coordinates (AAA and BBBB).
        """
        match = re.match(r"1km..(\d{3})0(\d{4})020..LLAKEERIE\.las", filename)
        if match:
            x = int(match.group(1)) * 1000
            y = int(match.group(2)) * 1000
            return x, y
        return None


    def find_neighbors_ON(files, x, y):
        """
        Find neighboring files based on UTM17 coordinates.
        """
        neighbors = []
        for file in files:
            coords = parse_filename_ON(file)
            if coords:
                nx, ny = coords
                if abs(nx - x) <= 1000 and abs(ny - y) <= 1000:  # Neighboring tiles
                    neighbors.append(file)
        return neighbors


    daydict = {} # Let's create a dictionnary with the day of lidar acquisition as key and list of las files
    for r, d, f in os.walk(input_folder):
        for file in f:
            if (file[-4:] == '.laz' or file[-4:] == '.las'):
                day = r[len(input_folder)+1:]
                if day not in daydict.keys():
                    daydict[day] = []
                daydict[day].append(file)

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    for day, laslist in daydict.items():

        if not os.path.exists(os.path.join(output_folder, day)):
            os.makedirs(os.path.join(output_folder, day))

        # Process each LAS file
        for file in laslist:
            print(day+"/"+file)
            full_path_input_file = os.path.join(input_folder, day, file)
            with laspy.open(full_path_input_file) as las:
                # Get the minimum x and y values of the LAS file
                min_x, min_y, min_z = las.header.mins
                max_x, max_y, max_z = las.header.maxs
                # Snap to the reference raster
                min_x = snap_ref_x - math.ceil((snap_ref_x - min_x) / cellsize) * cellsize
                min_y = snap_ref_y - math.ceil((snap_ref_y - min_y) / cellsize) * cellsize

            output_rasterfile = os.path.join(output_folder, day, file[:-4] + ".tif")

            coords = parse_filename_ON(file)
            x, y = coords
            neighbors = find_neighbors_ON(laslist, x, y)

            # Define the PDAL pipeline
            neighbors_full_path = [os.path.join(input_folder, day, neighbor) for neighbor in neighbors]
            pipeline = neighbors_full_path
            pipeline.append({
                        "type": "filters.merge"
                    })
            pipeline.append({
                "type": "filters.delaunay"  # Create a TIN from the LAS points
            })
            pipeline.append( {
                        "type": "filters.faceraster",  # Interpolate the TIN to create a raster
                        "resolution": cellsize,  # Set the raster resolution (cell size)
                        "origin_x": min_x,  # Set the origin of the raster
                        "origin_y": min_y,
                        "width": math.ceil((max_x - min_x) / cellsize),  # Set the width of the raster
                        "height": math.ceil((max_y - min_y) / cellsize)  # Set the height of the raster
                    })
            pipeline.append({
                        "type": "writers.raster",  # Save the raster as a GeoTIFF
                        "filename": output_rasterfile,
                        "gdaldriver": "GTiff",  # Use GeoTIFF format
                        "data_type": "Float32"  # Set the data type of the raster
                    })
            pipeline = {
                "pipeline": pipeline
            }

            # Run the PDAL pipeline
            result = subprocess.run(["pdal", "pipeline", "--stdin"], input=json.dumps(pipeline), text=True,
                                    capture_output=True)

            # Fill voids using python-GDAL
            # That could also be done with scipy.interpolate.griddata. I haven't tried yet.
            driver = gdal.GetDriverByName('GTiff')
            filled_rasterfile = os.path.splitext(output_rasterfile)[0] + "_filled.tif"
            dataset = gdal.Open(output_rasterfile)
            filled_dataset = driver.CreateCopy(filled_rasterfile, dataset, 0)
            gdal.FillNodata(targetBand=filled_dataset.GetRasterBand(1), maskBand=None,
                            maxSearchDist=1000, smoothingIterations=0)
            print(filled_rasterfile + " created")


def execute_mergelas(input_folder, output_folder):
    # Merge all LAS files by day of LiDAR acquisition into a single LAS file per day.

    # This function should not used for large datasets, as it creates a single file that is too large to handle.
    # Instead, execute_convertbytile should be used in order to convert LAS files into DEMs with preliminary merging
    # of the neighboring tiles. Then, the DEMs by tiles can be merged together.

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

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

def execute_lastoraster(input_folder, output_folder, footprint_folder, cellsize):
    # Convert LAS files into DEMs by creating a TIN from the LAS points and then interpolating the TIN to create a raster.
    # To be used after execute_mergelas
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
                    "type": "filters.crop",
                    "shape": os.path.join(footprint_folder, "footprint_"+file[:-4] +".shp")
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