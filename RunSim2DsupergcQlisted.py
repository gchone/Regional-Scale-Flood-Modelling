# -*- coding: utf-8 -*-


#####################################################
# Guénolé Choné
# Concordia University
# Geography, Planning and Environment Department
# guenole.chone@concordia.ca
#####################################################

import os
import arcpy
import subprocess
import shutil
import csv
import math
from datetime import datetime
from RasterIO import *

class pointflowpath:
   pass

def log_message(filelog, level, message):
    """
    Write formatted log messages with timestamp.

    Parameters:
        filelog: Log file handle
        level: Message level ('INFO', 'WARNING', 'ERROR')
        message: Message text
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{timestamp}] [{level}] {message}\n"
    filelog.write(formatted_msg)
    filelog.flush()

def check_mass_file(mass_file_path, lastdischarge, zonename, filelog, messages, tolerance=0.05):
    """
    Check the mass file to verify that Qin and Qout are similar and match lastdischarge.

    Parameters:
        mass_file_path: Path to the .mass file
        lastdischarge: The expected discharge value
        zonename: Zone name for logging
        filelog: Log file handle
        messages: ArcGIS messages object
        tolerance: Tolerance for comparison (default 5%)

    Returns:
        Boolean indicating if all checks passed
    """
    try:
        if not os.path.exists(mass_file_path):
            log_message(filelog, "WARNING", f"Mass file not found for {zonename}: {mass_file_path}")
            messages.addWarningMessage(f"[Mass Balance] Mass file not found for {zonename}: {mass_file_path}")
            return False

        # Read the mass file and extract the last line (final state)
        try:
            with open(mass_file_path, 'r') as f:
                lines = f.readlines()
        except IOError as e:
            log_message(filelog, "ERROR", f"Cannot read mass file for {zonename}: {str(e)}")
            messages.addErrorMessage(f"[Mass Balance] Cannot read mass file for {zonename}: {str(e)}")
            return False

        # Skip header and empty lines, get the last data line
        data_lines = [line for line in lines if line.strip() and not line.startswith('Time')]
        if not data_lines:
            log_message(filelog, "WARNING", f"No data found in mass file for {zonename}")
            messages.addWarningMessage(f"[Mass Balance] No data found in mass file for {zonename}")
            return False

        last_line = data_lines[-1].split()

        # Extract Qin and Qout (columns 7 and 9, 0-indexed: Time, Tstep, MinTstep, NumTsteps, Area, Vol, Qin, Hds, Qout)
        try:
            qin = float(last_line[6])   # Qin column (index 6)
            qout = float(last_line[8])  # Qout column (index 8)
        except (ValueError, IndexError) as e:
            log_message(filelog, "ERROR", f"Cannot parse Qin/Qout from mass file for {zonename}. Expected at least 9 columns. Error: {str(e)}")
            messages.addErrorMessage(f"[Mass Balance] Cannot parse Qin/Qout from mass file for {zonename}")
            return False

        all_checks_passed = True

        # Check 1: Qin and Qout are similar (within 5% tolerance)
        if qin != 0:
            qin_qout_diff = abs(qout - qin) / abs(qin)
        else:
            qin_qout_diff = abs(qout - qin)

        if qin_qout_diff > tolerance:
            all_checks_passed = False
            diff_pct = qin_qout_diff * 100
            msg = f"Qin and Qout mismatch for {zonename}: Qin={qin:.3f} m³/s, Qout={qout:.3f} m³/s, Difference={diff_pct:.2f}% (tolerance={tolerance*100:.1f}%)"
            log_message(filelog, "WARNING", msg)
            messages.addWarningMessage(f"[Mass Balance] {msg}")

        # Check 2: Qin match lastdischarge (within 5% tolerance)
        if lastdischarge != 0:
            qin_discharge_diff = abs(qin - lastdischarge) / abs(lastdischarge)
            qout_discharge_diff = abs(qout - lastdischarge) / abs(lastdischarge)
        else:
            qin_discharge_diff = abs(qin - lastdischarge)
            qout_discharge_diff = abs(qout - lastdischarge)

        if qin_discharge_diff > tolerance:
            all_checks_passed = False
            diff_pct = qin_discharge_diff * 100
            msg = f"Qin does not match inbci discharge for {zonename}: Qin={qin:.3f} m³/s, inbci discharge={lastdischarge:.3f} m³/s, Difference={diff_pct:.2f}% (tolerance={tolerance*100:.1f}%)"
            log_message(filelog, "WARNING", msg)
            messages.addWarningMessage(f"[Mass Balance] {msg}")

        return all_checks_passed

    except Exception as e:
        log_message(filelog, "ERROR", f"Unexpected exception in check_mass_file for {zonename}: {type(e).__name__}: {str(e)}")
        messages.addErrorMessage(f"[Mass Balance] Unexpected error for {zonename}: {str(e)}")
        return False

def check_simulation_time(mass_file_path, zonename, filelog, messages):
    """
    Check if the simulation stopped before time 55000, which indicates it may need to be rerun without steady state.

    Parameters:
        mass_file_path: Path to the .mass file
        zonename: Zone name for logging
        filelog: Log file handle
        messages: ArcGIS messages object

    Returns:
        Boolean - True if simulation stopped before time 55000, False otherwise
    """
    try:
        if not os.path.exists(mass_file_path):
            return False

        # Read the mass file
        try:
            with open(mass_file_path, 'r') as f:
                lines = f.readlines()
        except IOError as e:
            log_message(filelog, "WARNING", f"Cannot read mass file for simulation time check: {str(e)}")
            return False

        # Skip header and empty lines, get the last data line
        data_lines = [line for line in lines if line.strip() and not line.startswith('Time')]
        if not data_lines:
            return False

        last_line = data_lines[-1].split()

        # Extract Time (first column, index 0)
        try:
            time_value = float(last_line[0])
            if time_value <= 55000:
                log_message(filelog, "WARNING", f"Simulation for {zonename} stopped before time 55000 (steady state not reached). Will retry without -steady flag.")
                messages.addWarningMessage(f"[Simulation] Simulation for {zonename} stopped before time 55000. Retrying without steady state parameters.")
                return True
        except (ValueError, IndexError) as e:
            log_message(filelog, "WARNING", f"Cannot parse Time from mass file for {zonename}: {str(e)}")
            return False

        return False

    except Exception as e:
        log_message(filelog, "WARNING", f"Unexpected exception in check_simulation_time for {zonename}: {type(e).__name__}: {str(e)}")
        return False

def execute_RunSim_prev(str_zonefolder, str_simfolder, str_lisfloodfolder, str_lakes, list_fields_z, voutput, simtime, cfl, channelmanning, r_zbed, list_fieldQ_inbci, str_log, messages):

    # Max size of the output window (m). Effective size is latter reduced to 1/4 of the perimeter of the zone, if smaller
    max_distoutput = 4000

    str_inbci = str_zonefolder + "\\inbci.shp"
    str_outbci = str_zonefolder + "\\outbci.shp"
    zbed = RasterIO(r_zbed)

    # Count is used for the progress bar
    count = 0

    # Reading inbci.shp and creating a dictionary of inbci point by zone
    field_names = ["SHAPE@", "zoneid", "flowacc", "type", "fpid"]
    fieldQ_num = len(field_names)  # Position of the first field of the Q values in inbci.shp

    field_names.extend(list_fieldQ_inbci)
    bcipointcursor = arcpy.da.SearchCursor(str_inbci, field_names)
    dictsegmentsin = {}
    for point in bcipointcursor:
        if point[1] not in dictsegmentsin:
            dictsegmentsin[point[1]] = []
        dictsegmentsin[point[1]].append(point)

    # Zones sorted by id
    allzones = list(dictsegmentsin.keys())
    allzones.sort()

    # Creation of a dictionary of zones by from point id
    dictzones_fp = {}
    for zone in allzones:
        if dictsegmentsin[zone][0][4] not in dictzones_fp:
            dictzones_fp[dictsegmentsin[zone][0][4]] = []
        dictzones_fp[dictsegmentsin[zone][0][4]].append(zone)

    # Creation of a sorted list of zones ids, starting from the most downstream ones
    # Works because of the way the zones are created (by from point, starting upstream and going downstream)
    sortedzones = []
    listfp = list(dictzones_fp.keys()) # list of from point ids
    listfp.sort()
    for fp in listfp: # For each from point ...
        listzones_fp = dictzones_fp[fp]
        listzones_fp.sort(reverse=True) # ... take the list of zones ids in reverse order (lowest number = upstream)
        sortedzones.extend(listzones_fp)

    # Creating a dictionary of outbci.shp by zone
    listzonesout = {}
    bcipointcursor = arcpy.da.SearchCursor(str_outbci, ["zoneid", "side", "SHAPE@"])
    for point in bcipointcursor:
        listzonesout[point[0]] = point

    # Creating a dictionary of maximum output window size by zone and one of lake id by zone (if any)
    zones = str_zonefolder + "\\envelopezones.shp"
    dict_outputwindow = {}
    zonesscursor = arcpy.da.SearchCursor(zones, ["GRID_CODE", "SHAPE@", "Lake_ID"])
    lakeid_byzone = {}
    for zoneshp in zonesscursor:
        # Reading and storing lake id if any
        if zoneshp[2] != -999:
            lakeid_byzone[zoneshp[0]] = zoneshp[2]
        # Computing the zone permimeter and adjusting the output window size if needed (max 1/4 of the permimeter)
        Xmin = zoneshp[1].extent.XMin
        Ymin = zoneshp[1].extent.YMin
        Xmax = zoneshp[1].extent.XMax
        Ymax = zoneshp[1].extent.YMax
        perimeter = 2 * ((Xmax - Xmin) + (Ymax - Ymin))
        dict_outputwindow[zoneshp[0]] = min(max_distoutput, perimeter / 4.)

    # Creating a dictionary of lake z values by lake id
    lakefields = [arcpy.Describe(str_lakes).OIDFieldName]
    lakefields.extend(list_fields_z)
    shplakes = arcpy.da.SearchCursor(str_lakes, lakefields)
    fieldz_bylakeid = {}
    for shplake in shplakes:
        fieldz_bylakeid[shplake[0]] = shplake[1:]

    # Progress bar
    arcpy.SetProgressor("step", "Simulation 2D", 0, count, 1)
    progres = 0
    arcpy.SetProgressorPosition(progres)

    filelog = open(str_log, 'w')

    ref_raster = None

    # Starting the loop on discharges fields
    Q_iteration = -1
    for fieldQ in list_fieldQ_inbci:
        Q_iteration +=1
        simname = fieldQ
        currentsimfolder = str_simfolder + "\\" + simname
        currentresult = str_simfolder + "\\res_" + simname + ".tif"

        skipsim = False # Used when a simulation produced no output
        if arcpy.Exists(currentresult):
            log_message(filelog, "INFO", f"Simulation result already exists for {simname}. Skipping simulation.")
            skipsim = True
        else:

            filelog.write(f"Starting simulations with discharge field: {simname}\n")

            if not os.path.isdir(currentsimfolder):
                os.makedirs(currentsimfolder)

            # For each zone (ordered from downstream to upstream)
            for zone in sortedzones:
                segment = dictsegmentsin[zone]
                # Going through the inbci point, ordered by flowacc (from upstream to downstream)
                for point in sorted(segment, key=lambda q: q[2]):

                    if point[3]=="main" and not skipsim: # Main inbci point = a simulation needs to be run

                        if not arcpy.Exists(currentsimfolder + "\\elev_zone" + str(point[1]) + ".tif"):

                            print("Running simulation on zone " + str(point[1]))
                            distoutput = dict_outputwindow[point[1]]

                            # ref_raster is the dem of the current zone, used for cell size and extent
                            ref_raster = RasterIO(arcpy.Raster(str_zonefolder + "\\zone" + str(point[1]) + ".tif"))

                            # Looking for the downstream elevation, either from a lake or from the previous simulation result
                            lakebci = False
                            if point[1] in lakeid_byzone:
                                hfix = fieldz_bylakeid[lakeid_byzone[point[1]]][Q_iteration]
                                lakebci = True
                            else:
                                if not os.path.exists(currentresult):
                                    messages.addErrorMessage("Downsteam boudary condition not found: tile #" + str(point[1]))
                                    filelog.write("ERROR: Downsteam boudary condition not found: tile #" + str(point[1]) + "\n")
                                else:
                                    # issue with Mosaic_management, used later with lisflood_res:
                                    # crash sometimes if the file is read here
                                    # so we make a tmp copy
                                    if arcpy.Exists(currentsimfolder + "\\tmp_zone"  + str(point[1]) + ".tif"):
                                        arcpy.Delete_management(currentsimfolder + "\\tmp_zone"  + str(point[1]) + ".tif")
                                    arcpy.Copy_management(currentresult, currentsimfolder + "\\tmp_zone" + str(point[1]) + ".tif")
                                    res_downstream = RasterIO(arcpy.Raster(currentsimfolder + "\\tmp_zone"  + str(point[1]) + ".tif"))
                                    lakebci = False

                            # The .bci file, from the template, will be copied and modified
                            sourcebci = str_simfolder + "\\zone" + str(point[1]) + ".bci"
                            destinationbci = currentsimfolder + "\\zone" + str(point[1]) + ".bci"
                            if os.path.isfile(destinationbci):
                                os.remove(destinationbci)
                            shutil.copy(sourcebci, destinationbci)

                            # Remove all downstream boundary conditions in the bci file (lines that do not start with 'P')
                            with open(destinationbci, 'r') as f:
                                lines = f.readlines()
                            with open(destinationbci, 'w') as f:
                                for line in lines:
                                    if line.strip() and line[0] == 'P':
                                        f.write(line)

                            filebci = open(destinationbci, 'a')


                            # bdy file creation
                            newfilebdy = currentsimfolder + "\\zone" + str(point[1]) + ".bdy"
                            for point2 in sorted(segment, key=lambda q: q[2]):
                                q_value = point2[fieldQ_num + Q_iteration]
                                if point2[3] == "main":
                                    pointdischarge = q_value / (
                                    (ref_raster.raster.meanCellHeight + ref_raster.raster.meanCellWidth) / 2)
                                    lastdischarge = q_value
                                    latnum = 0
                                    filebdy = open(newfilebdy, 'w')
                                    filebdy.write("zone"+str(point[1]) + ".bdy\n")
                                    filebdy.write("zone"+str(point[1]) + "\n")
                                    filebdy.write("3\tseconds\n")
                                    filebdy.write("0\t0\n")
                                    filebdy.write("{0:.3f}".format(pointdischarge) + "\t50000\n")
                                    filebdy.write("{0:.3f}".format(pointdischarge) + "\t" + str(simtime))
                                    filebdy.close()
                                else:
                                    latnum += 1
                                    pointdischarge = (q_value - lastdischarge) / (
                                    (ref_raster.raster.meanCellHeight + ref_raster.raster.meanCellWidth) / 2)
                                    lastdischarge = q_value
                                    filebdy = open(newfilebdy, 'a')
                                    filebdy.write("\nzone" + str(point[1]) + "_" + str(latnum) + "\n")
                                    filebdy.write("3\tseconds\n")
                                    filebdy.write("0\t0\n")
                                    filebdy.write("{0:.3f}".format(pointdischarge) + "\t50000\n")
                                    filebdy.write("{0:.3f}".format(pointdischarge) + "\t" + str(simtime))
                                    filebdy.close()
                            filebdy = open(newfilebdy, 'a')



                            ### Looking for what is at the downstream end of the zone ###
                            numhvar = 1
                            newpoint = pointflowpath()
                            newpoint.side = listzonesout[point[1]][1] # 'N', 'S', 'E' or 'W'
                            newpoint.shape = listzonesout[point[1]][2].firstPoint # output point geometry
                            colinc = 0
                            rowinc = 0
                            distinc = 0
                            newpoint.side2 = "0"
                            newpoint.lim3 = 0
                            newpoint.lim4 = 0

                            # Starting at the outbci point, going in one direction first (either horizontally or vertically)
                            currentcol = ref_raster.XtoCol(newpoint.shape.X)
                            currentrow = ref_raster.YtoRow(newpoint.shape.Y)
                            if newpoint.side == "W" or newpoint.side == "E":
                                rowinc = 1
                                distinc = ref_raster.raster.meanCellHeight
                                newpoint.lim1 = newpoint.shape.Y - distinc / 2.
                            else:
                                colinc = 1
                                distinc = ref_raster.raster.meanCellWidth
                                newpoint.lim1 = newpoint.shape.X + distinc / 2.
                            distance = 0

                            if not lakebci:
                                hresult_row = res_downstream.YtoRow(newpoint.shape.Y)
                                hresult_col = res_downstream.XtoCol(newpoint.shape.X)
                                # Looking at the cell elevation just outside of the zone
                                if newpoint.side == "W":
                                    hresult_col -= 1
                                elif newpoint.side == "E":
                                    hresult_col += 1
                                elif newpoint.side == "N":
                                    hresult_row -= 1
                                elif newpoint.side == "S":
                                    hresult_row += 1
                                hfix = res_downstream.getValue(hresult_row, hresult_col)
                                if hfix != res_downstream.nodata:
                                    # Adding a line in the bci file
                                    if newpoint.side == "N" or newpoint.side == "S":
                                        filebci.write(
                                            newpoint.side + "\t" + "{0:.2f}".format(newpoint.shape.X+distinc/2.) + "\t" + "{0:.2f}".format(newpoint.shape.X-distinc/2.) + "\tHVAR\thvar" + str(numhvar) + "\n")
                                    else:
                                        filebci.write(
                                            newpoint.side + "\t" + "{0:.2f}".format(
                                                newpoint.shape.Y + distinc / 2.) + "\t" + "{0:.2f}".format(
                                                newpoint.shape.Y - distinc / 2.) + "\tHVAR\thvar" + str(numhvar) + "\n")
                                    # Adding a line in the bdy file
                                    zdep = min(zbed.getValue(zbed.YtoRow(newpoint.shape.Y), zbed.XtoCol(newpoint.shape.X)) + 0.3, hfix)
                                    filebdy.write("\nhvar"+str(numhvar)+"\n")
                                    filebdy.write("4\tseconds\n")
                                    filebdy.write("{0:.2f}".format(zdep) + "\t0\n")
                                    filebdy.write("{0:.2f}".format(zdep) + "\t50000\n")
                                    filebdy.write("{0:.2f}".format(hfix) + "\t55000\n")
                                    filebdy.write("{0:.2f}".format(hfix) + "\t" + str(simtime))
                                    numhvar += 1


                            # Progressing until we exit the raster or until we reach the maximum distance allowed
                            while (not (
                                    currentcol < 0 or currentcol >= ref_raster.raster.width or currentrow < 0 or currentrow >= ref_raster.raster.height)) \
                                    and distance < distoutput / 2:
                                distance += distinc
                                currentrow += rowinc
                                currentcol += colinc
                                if newpoint.side == "W" or newpoint.side == "E":
                                    newpoint.lim1 = ref_raster.RowtoY(currentrow)
                                else:
                                    newpoint.lim1 = ref_raster.ColtoX(currentcol)
                                if not lakebci:
                                    hresult_row = res_downstream.YtoRow(ref_raster.RowtoY(currentrow))
                                    hresult_col = res_downstream.XtoCol(ref_raster.ColtoX(currentcol))
                                    # Looking at the cell elevation just outside of the zone
                                    if newpoint.side == "W":
                                        hresult_col -= 1
                                    elif newpoint.side == "E":
                                        hresult_col += 1
                                    elif newpoint.side == "N":
                                        hresult_row -= 1
                                    elif newpoint.side == "S":
                                        hresult_row += 1
                                    hfix = res_downstream.getValue(hresult_row, hresult_col)

                                    if hfix != res_downstream.nodata:
                                        # Adding a line in the bci file
                                        filebci.write(
                                            newpoint.side + "\t" + "{0:.2f}".format(newpoint.lim1 + distinc / 2.) + "\t" + "{0:.2f}".format(
                                                newpoint.lim1 - distinc / 2.) + "\tHVAR\thvar"+ str(numhvar)+ "\n")
                                        # Adding a line in the bdy file
                                        zdep = min(ref_raster.getValue(currentrow, currentcol) + 0.3, hfix)
                                        filebdy.write("\nhvar" + str(numhvar) + "\n")
                                        filebdy.write("4\tseconds\n")
                                        filebdy.write("{0:.2f}".format(zdep) + "\t0\n")
                                        filebdy.write("{0:.2f}".format(zdep) + "\t50000\n")
                                        filebdy.write("{0:.2f}".format(hfix) + "\t55000\n")
                                        filebdy.write("{0:.2f}".format(hfix) + "\t" + str(simtime))
                                        numhvar += 1

                            # Coordinates before exiting the raster
                            currentrow -= rowinc
                            currentcol -= colinc

                            # If we went out of the raster, we turn and go on on another face of the raster
                            if distance < distoutput / 2:
                                distance -= distinc
                                if newpoint.side == "W":
                                    colinc = 1
                                    rowinc = 0
                                    distinc = ref_raster.raster.meanCellWidth
                                    newpoint.lim3 = ref_raster.raster.extent.XMin + (
                                                currentcol + 0.5) * ref_raster.raster.meanCellWidth
                                    newpoint.side2 = "S"
                                elif newpoint.side == "E":
                                    colinc = -1
                                    rowinc = 0
                                    distinc = ref_raster.raster.meanCellWidth
                                    newpoint.lim3 = ref_raster.raster.extent.XMin + (
                                                currentcol + 0.5) * ref_raster.raster.meanCellWidth
                                    newpoint.side2 = "S"

                                elif newpoint.side == "N":
                                    rowinc = 1
                                    colinc = 0
                                    distinc = ref_raster.raster.meanCellHeight
                                    newpoint.lim3 = max(ref_raster.raster.extent.YMin, ref_raster.raster.extent.YMax - (
                                                currentrow + 1) * ref_raster.raster.meanCellHeight) + 0.5 * ref_raster.raster.meanCellHeight
                                    newpoint.side2 = "E"
                                elif newpoint.side == "S":
                                    rowinc = -1
                                    colinc = 0
                                    distinc = ref_raster.raster.meanCellHeight
                                    newpoint.lim3 = max(ref_raster.raster.extent.YMin, ref_raster.raster.extent.YMax - (
                                                currentrow + 1) * ref_raster.raster.meanCellHeight) + 0.5 * ref_raster.raster.meanCellHeight
                                    newpoint.side2 = "E"
                                # On progresse à nouveau jusqu'à sortir du raster ou jusqu'à ce que la distance voulue soit attente
                                while (not (
                                        currentcol < 0 or currentcol >= ref_raster.raster.width or currentrow < 0 or currentrow >= ref_raster.raster.height)) \
                                        and ref_raster.getValue(currentrow,
                                                            currentcol) != ref_raster.nodata and distance < distoutput / 2:
                                    distance += distinc
                                    currentrow += rowinc
                                    currentcol += colinc

                                    if newpoint.side2 == "W" or newpoint.side2 == "E":
                                        newpoint.lim4 = ref_raster.RowtoY(currentrow)
                                    else:
                                        newpoint.lim4 = ref_raster.ColtoX(currentcol)
                                    if not lakebci:
                                        hresult_row = res_downstream.YtoRow(ref_raster.RowtoY(currentrow))
                                        hresult_col = res_downstream.XtoCol(ref_raster.ColtoX(currentcol))
                                        # Looking at the cell elevation just outside of the zone
                                        if newpoint.side == "W":
                                            hresult_col -= 1
                                        elif newpoint.side == "E":
                                            hresult_col += 1
                                        elif newpoint.side == "N":
                                            hresult_row -= 1
                                        elif newpoint.side == "S":
                                            hresult_row += 1
                                        hfix = res_downstream.getValue(hresult_row, hresult_col)

                                        if hfix != res_downstream.nodata:
                                            # Adding a line in the bci file
                                            filebci.write(
                                                newpoint.side2 + "\t" + "{0:.2f}".format(
                                                    newpoint.lim4 + distinc / 2.) + "\t" + "{0:.2f}".format(
                                                    newpoint.lim4 - distinc / 2.) + "\tHVAR\thvar" + str(numhvar)+ "\n")
                                            # Adding a line in the bdy file
                                            zdep = min(ref_raster.getValue(currentrow, currentcol) + 0.3, hfix)
                                            filebdy.write("\nhvar" + str(numhvar) + "\n")
                                            filebdy.write("4\tseconds\n")
                                            filebdy.write("{0:.2f}".format(zdep) + "\t0\n")
                                            filebdy.write("{0:.2f}".format(zdep) + "\t50000\n")
                                            filebdy.write("{0:.2f}".format(hfix) + "\t55000\n")
                                            filebdy.write("{0:.2f}".format(hfix) + "\t" + str(simtime))
                                            numhvar += 1
                                currentrow -= rowinc
                                currentcol -= colinc
                                if lakebci:
                                    # Adding a line in the bci file, for the lake
                                    filebci.write(
                                        newpoint.side2 + "\t" + "{0:.2f}".format(newpoint.lim3) + "\t" + "{0:.2f}".format(
                                            newpoint.lim4) + "\tHVAR\thvar" + "\n")

                            # Starting again on the other direction from the outbci point
                            colinc = 0
                            rowinc = 0
                            distinc = 0
                            if newpoint.side == "W" or newpoint.side == "E":
                                rowinc = -1
                                distinc = ref_raster.raster.meanCellHeight
                                newpoint.lim2 = newpoint.shape.Y + distinc / 2.
                            else:
                                colinc = -1
                                distinc = ref_raster.raster.meanCellWidth
                                newpoint.lim2 = newpoint.shape.X - distinc / 2.
                            currentcol = ref_raster.XtoCol(newpoint.shape.X)
                            currentrow = ref_raster.YtoRow(newpoint.shape.Y)
                            distance = 0
                            while (not (
                                    currentcol < 0 or currentcol >= ref_raster.raster.width or currentrow < 0 or currentrow >= ref_raster.raster.height)) \
                                    and ref_raster.getValue(currentrow,
                                                        currentcol) != ref_raster.nodata and distance < distoutput / 2:
                                distance += distinc
                                currentrow += rowinc
                                currentcol += colinc
                                if newpoint.side == "W" or newpoint.side == "E":
                                    newpoint.lim2 = ref_raster.RowtoY(currentrow)
                                else:
                                    newpoint.lim2 = ref_raster.ColtoX(currentcol)
                                if not lakebci:
                                    hresult_row = res_downstream.YtoRow(ref_raster.RowtoY(currentrow))
                                    hresult_col = res_downstream.XtoCol(ref_raster.ColtoX(currentcol))
                                    # Looking at the cell elevation just outside of the zone
                                    if newpoint.side == "W":
                                        hresult_col -= 1
                                    elif newpoint.side == "E":
                                        hresult_col += 1
                                    elif newpoint.side == "N":
                                        hresult_row -= 1
                                    elif newpoint.side == "S":
                                        hresult_row += 1
                                    hfix = res_downstream.getValue(hresult_row, hresult_col)
                                    if hfix != res_downstream.nodata:

                                        filebci.write(
                                            newpoint.side + "\t" + "{0:.2f}".format(
                                                newpoint.lim2 + distinc / 2.) + "\t" + "{0:.2f}".format(
                                                newpoint.lim2 - distinc / 2.) + "\tHVAR\thvar" + str(numhvar)+ "\n")

                                        zdep = min(ref_raster.getValue(currentrow, currentcol) + 0.3, hfix)
                                        filebdy.write("\nhvar" + str(numhvar) + "\n")
                                        filebdy.write("4\tseconds\n")
                                        filebdy.write("{0:.2f}".format(zdep) + "\t0\n")
                                        filebdy.write("{0:.2f}".format(zdep) + "\t50000\n")
                                        filebdy.write("{0:.2f}".format(hfix) + "\t55000\n")
                                        filebdy.write("{0:.2f}".format(hfix) + "\t" + str(simtime))
                                        numhvar += 1
                            currentrow -= rowinc
                            currentcol -= colinc


                            if distance < distoutput / 2:
                                distance -= distinc
                                if newpoint.side == "W":
                                    colinc = 1
                                    rowinc = 0
                                    distinc = ref_raster.raster.meanCellWidth
                                    newpoint.lim3 = ref_raster.raster.extent.XMin + (
                                                currentcol + 0.5) * ref_raster.raster.meanCellWidth
                                    newpoint.side2 = "N"
                                elif newpoint.side == "E":
                                    colinc = -1
                                    rowinc = 0
                                    distinc = ref_raster.raster.meanCellWidth
                                    newpoint.lim3 = ref_raster.raster.extent.XMin + (
                                                currentcol + 0.5) * ref_raster.raster.meanCellWidth
                                    newpoint.side2 = "N"
                                elif newpoint.side == "N":
                                    rowinc = 1
                                    colinc = 0
                                    distinc = ref_raster.raster.meanCellHeight
                                    newpoint.lim3 = max(ref_raster.raster.extent.YMin, ref_raster.raster.extent.YMax - (
                                                currentrow + 1) * ref_raster.raster.meanCellHeight) + 0.5 * ref_raster.raster.meanCellHeight
                                    newpoint.side2 = "W"
                                elif newpoint.side == "S":
                                    rowinc = -1
                                    colinc = 0
                                    distinc = ref_raster.raster.meanCellHeight
                                    newpoint.lim3 = max(ref_raster.raster.extent.YMin, ref_raster.raster.extent.YMax - (
                                                currentrow + 1) * ref_raster.raster.meanCellHeight) + 0.5 * ref_raster.raster.meanCellHeight
                                    newpoint.side2 = "W"
                                while (not (
                                        currentcol < 0 or currentcol >= ref_raster.raster.width or currentrow < 0 or currentrow >= ref_raster.raster.height)) \
                                        and ref_raster.getValue(currentrow,
                                                            currentcol) != ref_raster.nodata and distance < distoutput / 2:
                                    distance += distinc
                                    currentrow += rowinc
                                    currentcol += colinc

                                    if newpoint.side2 == "W" or newpoint.side2 == "E":
                                        newpoint.lim4 = ref_raster.RowtoY(currentrow)
                                    else:
                                        newpoint.lim4 = ref_raster.ColtoX(currentcol)
                                    if not lakebci:
                                        hresult_row = res_downstream.YtoRow(ref_raster.RowtoY(currentrow))
                                        hresult_col = res_downstream.XtoCol(ref_raster.ColtoX(currentcol))
                                        # Looking at the cell elevation just outside of the zone
                                        if newpoint.side == "W":
                                            hresult_col -= 1
                                        elif newpoint.side == "E":
                                            hresult_col += 1
                                        elif newpoint.side == "N":
                                            hresult_row -= 1
                                        elif newpoint.side == "S":
                                            hresult_row += 1
                                        hfix = res_downstream.getValue(hresult_row, hresult_col)

                                        if hfix != res_downstream.nodata:

                                            filebci.write(
                                                newpoint.side2 + "\t" + "{0:.2f}".format(
                                                    newpoint.lim4 + distinc / 2.) + "\t" + "{0:.2f}".format(
                                                    newpoint.lim4 - distinc / 2.) + "\tHVAR\thvar" + str(numhvar)+ "\n")

                                            zdep = min(ref_raster.getValue(currentrow, currentcol) + 0.3, hfix)

                                            filebdy.write("\nhvar" + str(numhvar) + "\n")
                                            filebdy.write("4\tseconds\n")
                                            filebdy.write("{0:.2f}".format(zdep) + "\t0\n")
                                            filebdy.write("{0:.2f}".format(zdep) + "\t50000\n")
                                            filebdy.write("{0:.2f}".format(hfix) + "\t55000\n")
                                            filebdy.write("{0:.2f}".format(hfix) + "\t" + str(simtime))
                                            numhvar += 1
                                currentrow -= rowinc
                                currentcol -= colinc
                                if lakebci:

                                    filebci.write(
                                        newpoint.side2 + "\t" + "{0:.2f}".format(newpoint.lim3) + "\t" + "{0:.2f}".format(
                                            newpoint.lim4) + "\tHVAR\thvar" + "\n")


                            if lakebci:
                                # Adding a line in the bci file, for the lake
                                filebci.write(
                                    newpoint.side + "\t" + "{0:.2f}".format(newpoint.lim1) + "\t" + "{0:.2f}".format(
                                        newpoint.lim2) + "\tHVAR\thvar"+ "\n")

                                # Adding also the needed line in the bdy file
                                zdep = min(zbed.getValue(zbed.YtoRow(newpoint.shape.Y), zbed.XtoCol(newpoint.shape.X)) + 0.3, hfix)
                                filebdy.write("\nhvar\n")
                                filebdy.write("4\tseconds\n")
                                filebdy.write("{0:.2f}".format(zdep) + "\t0\n")
                                filebdy.write("{0:.2f}".format(zdep) + "\t50000\n")
                                filebdy.write("{0:.2f}".format(hfix) + "\t55000\n")
                                filebdy.write("{0:.2f}".format(hfix) + "\t" + str(simtime))
                                numhvar += 1

                            filebci.close()
                            filebdy.close()
                            ### End of the downstream boundaries processing ###

                            # par file creation
                            newfile = str_simfolder + "\\zone" + str(point[1]) + ".par"
                            if os.path.isfile(newfile):
                                os.remove(newfile)

                            filepar = open(newfile, 'w')
                            filepar.write("DEMfile\tzone" + str(point[1]) + ".txt\n")
                            filepar.write("resroot\tzone" + str(point[1]) + "\n")
                            filepar.write("dirroot\t" + simname + "\n")
                            filepar.write("manningfile\tnzone" + str(point[1]) + ".txt\n")
                            filepar.write("bcifile\t"+ simname +"\\zone" + str(point[1]) + ".bci" + "\n")
                            filepar.write("sim_time\t" + str(simtime) + "\n")
                            filepar.write("saveint\t" + str(simtime) + "\n")
                            filepar.write("bdyfile\t"+ simname +"\\zone" + str(point[1]) + ".bdy" + "\n")
                            filepar.write("SGCwidth\twzone" + str(point[1]) + ".txt\n")
                            filepar.write("SGCbank\tzone" + str(point[1]) + ".txt\n")
                            filepar.write("SGCbed\tdzone" + str(point[1]) + ".txt\n")
                            filepar.write("SGCn\t" + str(channelmanning) + "\n")

                            filepar.write("chanmask\tmzone" + str(point[1]) + ".txt\n")

                            # outputing velocities?
                            if voutput:
                                filepar.write("hazard\n")
                                filepar.write("qoutput\n")
                            filepar.write("cfl\t" + str(cfl) + "\n")
                            filepar.write("max_Froude\t1\n")
                            # filepar.write("debug\n")
                            filepar.close()



                            # Defining the -steadytol parameter of LISFLOOD-FP
                            # Hardcoded as 1/200th of the discharge
                            try:
                                steadytol = str(
                                    round(lastdischarge / 200., - int(math.floor(math.log10(abs(lastdischarge / 200.))))))
                            except (ValueError, ZeroDivisionError) as e:
                                log_message(filelog, "ERROR", f"Cannot calculate steadytol for zone {point[1]}, sim {simname}: {str(e)}")
                                messages.addErrorMessage(f"[LISFLOOD] Cannot calculate steadytol for zone {point[1]}")
                                skipsim = True
                                continue

                            # Running LISFLOOD-FP
                            log_message(filelog, "INFO", f"Starting LISFLOOD-FP simulation for zone {point[1]}, sim {simname} (steadytol={steadytol})")
                            try:
                                result = subprocess.run(
                                    [str_lisfloodfolder + "\\lisflood.exe", "-steady", "-steadytol", steadytol,
                                     str_simfolder + "\\zone" + str(point[1]) + ".par"],
                                    shell=True, cwd=str_simfolder, capture_output=True, text=True, timeout=3600
                                )
                                if result.returncode != 0:
                                    log_message(filelog, "ERROR", f"LISFLOOD-FP failed for zone {point[1]}, sim {simname}. Return code: {result.returncode}")
                                    if result.stderr:
                                        log_message(filelog, "ERROR", f"LISFLOOD stderr: {result.stderr[:500]}")
                                    messages.addErrorMessage(f"[LISFLOOD] LISFLOOD-FP simulation failed for zone {point[1]}")
                                    skipsim = True
                                    continue
                            except subprocess.TimeoutExpired:
                                log_message(filelog, "ERROR", f"LISFLOOD-FP timeout for zone {point[1]}, sim {simname} (> 1 hour)")
                                messages.addErrorMessage(f"[LISFLOOD] LISFLOOD-FP timeout for zone {point[1]}")
                                skipsim = True
                                continue
                            except Exception as e:
                                log_message(filelog, "ERROR", f"LISFLOOD-FP execution error for zone {point[1]}, sim {simname}: {type(e).__name__}: {str(e)}")
                                messages.addErrorMessage(f"[LISFLOOD] LISFLOOD-FP execution error for zone {point[1]}: {str(e)}")
                                skipsim = True
                                continue

                            progres += 1
                            arcpy.SetProgressorPosition(progres)
                            log_message(filelog, "INFO", f"LISFLOOD-FP simulation completed for zone {point[1]}, sim {simname}")

                            zonename = "zone" + str(point[1])
                            mass_file_path = currentsimfolder + "\\"  + zonename + ".mass"

                            # Check if simulation stopped at time 55000 and retry without -steady flag
                            if check_simulation_time(mass_file_path, zonename, filelog, messages):
                                log_message(filelog, "INFO", f"Retrying LISFLOOD-FP simulation for zone {point[1]} without -steady flag")

                                # Delete previous output files to ensure clean retry
                                output_files_to_remove = [
                                    currentsimfolder + "\\" + zonename + "-0001.elev",
                                    currentsimfolder + "\\" + zonename + "-9999.elev",
                                    currentsimfolder + "\\" + zonename + "-0001.Vx",
                                    currentsimfolder + "\\" + zonename + "-9999.Vx",
                                    currentsimfolder + "\\" + zonename + "-0001.Vy",
                                    currentsimfolder + "\\" + zonename + "-9999.Vy",
                                    mass_file_path
                                ]
                                for output_file in output_files_to_remove:
                                    if os.path.exists(output_file):
                                        try:
                                            os.remove(output_file)
                                        except Exception as e:
                                            log_message(filelog, "WARNING", f"Could not remove {output_file}: {str(e)}")

                                # Retry without -steady and -steadytol parameters
                                try:
                                    log_message(filelog, "INFO", f"Starting LISFLOOD-FP retry for zone {point[1]}, sim {simname} (without steady state parameters)")
                                    result = subprocess.run(
                                        [str_lisfloodfolder + "\\lisflood.exe",
                                         str_simfolder + "\\zone" + str(point[1]) + ".par"],
                                        shell=True, cwd=str_simfolder, capture_output=True, text=True, timeout=3600
                                    )
                                    if result.returncode != 0:
                                        log_message(filelog, "ERROR", f"LISFLOOD-FP retry failed for zone {point[1]}, sim {simname}. Return code: {result.returncode}")
                                        if result.stderr:
                                            log_message(filelog, "ERROR", f"LISFLOOD stderr: {result.stderr[:500]}")
                                        messages.addErrorMessage(f"[LISFLOOD] LISFLOOD-FP retry simulation failed for zone {point[1]}")
                                        skipsim = True
                                        continue
                                    else:
                                        log_message(filelog, "INFO", f"LISFLOOD-FP retry simulation completed successfully for zone {point[1]}, sim {simname}")
                                except subprocess.TimeoutExpired:
                                    log_message(filelog, "ERROR", f"LISFLOOD-FP retry timeout for zone {point[1]}, sim {simname} (> 1 hour)")
                                    messages.addErrorMessage(f"[LISFLOOD] LISFLOOD-FP retry timeout for zone {point[1]}")
                                    skipsim = True
                                    continue
                                except Exception as e:
                                    log_message(filelog, "ERROR", f"LISFLOOD-FP retry execution error for zone {point[1]}, sim {simname}: {type(e).__name__}: {str(e)}")
                                    messages.addErrorMessage(f"[LISFLOOD] LISFLOOD-FP retry execution error for zone {point[1]}: {str(e)}")
                                    skipsim = True
                                    continue

                            # Validate mass balance
                            try:
                                check_mass_file(mass_file_path, lastdischarge, zonename, filelog, messages)
                            except Exception as e:
                                log_message(filelog, "ERROR", f"Exception during mass balance validation for {zonename}: {type(e).__name__}: {str(e)}")
                                messages.addErrorMessage(f"[Mass Balance] Exception during validation for {zonename}: {str(e)}")

                            if arcpy.Exists(currentsimfolder + "\\tmp_zone" + str(point[1])):
                                arcpy.Delete_management(currentsimfolder + "\\tmp_zone" + str(point[1]))

                            # Converting output files
                            try:
                                if os.path.exists(currentsimfolder + "\\"  + zonename + "elev.txt"):
                                    os.remove(currentsimfolder + "\\"   + zonename + "elev.txt")

                                elev_file_found = False
                                if os.path.exists(currentsimfolder + "\\" + zonename + "-9999.elev"):
                                    os.rename(currentsimfolder + "\\" + zonename + "-9999.elev",
                                              currentsimfolder + "\\" + zonename + "elev.txt")
                                    elev_file_found = True
                                elif os.path.exists(currentsimfolder + "\\" + zonename + "-0001.elev"):
                                    os.rename(currentsimfolder + "\\" + zonename + "-0001.elev",
                                              currentsimfolder + "\\" + zonename + "elev.txt")
                                    elev_file_found = True
                                    log_message(filelog, "WARNING", f"Steady state not reached for {zonename}, sim {simname} (using -0001.elev)")
                                    messages.addWarningMessage(f"[Simulation] Steady state not reached for {zonename}, sim {simname}")
                                else:
                                    log_message(filelog, "ERROR", f"No elevation output file found for {zonename}")
                                    messages.addErrorMessage(f"[Output] No elevation output file found for {zonename}")
                                    skipsim = True
                                    continue

                                # Convert velocity files if available
                                if os.path.exists(currentsimfolder + "\\" + zonename + "-9999.Vx") or os.path.exists(currentsimfolder + "\\" + zonename + "-0001.Vx"):
                                    if os.path.exists(currentsimfolder + "\\" + zonename + "Vx.txt"):
                                        os.remove(currentsimfolder + "\\" + zonename + "Vx.txt")
                                    if os.path.exists(currentsimfolder + "\\" + zonename + "Vy.txt"):
                                        os.remove(currentsimfolder + "\\" + zonename + "Vy.txt")

                                    if os.path.exists(currentsimfolder + "\\" + zonename + "-9999.Vx"):
                                        os.rename(currentsimfolder + "\\" + zonename + "-9999.Vx",
                                                  currentsimfolder + "\\" + zonename + "Vx.txt")
                                        os.rename(currentsimfolder + "\\" + zonename + "-9999.Vy",
                                                  currentsimfolder + "\\" + zonename + "Vy.txt")
                                    else:
                                        os.rename(currentsimfolder + "\\" + zonename + "-0001.Vx",
                                                  currentsimfolder + "\\" + zonename + "Vx.txt")
                                        os.rename(currentsimfolder + "\\" + zonename + "-0001.Vy",
                                                  currentsimfolder + "\\" + zonename + "Vy.txt")

                                    try:
                                        arcpy.ASCIIToRaster_conversion(currentsimfolder + "\\" + zonename + "Vx.txt",
                                                                       currentsimfolder + "\\Vx_" + zonename + ".tif",
                                                                       "FLOAT")
                                        arcpy.ASCIIToRaster_conversion(currentsimfolder + "\\" + zonename + "Vy.txt",
                                                                       currentsimfolder + "\\Vy_" + zonename + ".tif",
                                                                       "FLOAT")
                                        arcpy.DefineProjection_management(currentsimfolder + "\\Vx_" + zonename + ".tif",
                                                                          ref_raster.raster.spatialReference)
                                        arcpy.DefineProjection_management(currentsimfolder + "\\Vy_" + zonename + ".tif",
                                                                          ref_raster.raster.spatialReference)
                                    except Exception as e:
                                        log_message(filelog, "WARNING", f"Could not create velocity rasters for {zonename}: {str(e)}")
                                        messages.addWarningMessage(f"[Output] Could not create velocity rasters for {zonename}")

                                # Creating elevation raster for ArcGIS
                                str_elev = currentsimfolder + "\\elev_" + zonename + ".tif"
                                try:
                                    arcpy.ASCIIToRaster_conversion(currentsimfolder + "\\" + zonename + "elev.txt", str_elev, "FLOAT")
                                    arcpy.DefineProjection_management(str_elev, ref_raster.raster.spatialReference)
                                except Exception as e:
                                    log_message(filelog, "ERROR", f"Failed to create elevation raster for {zonename}: {str(e)}")
                                    messages.addErrorMessage(f"[Output] Failed to create elevation raster for {zonename}: {str(e)}")
                                    skipsim = True
                                    continue

                            except Exception as e:
                                log_message(filelog, "ERROR", f"Error during output file conversion for {zonename}: {type(e).__name__}: {str(e)}")
                                messages.addErrorMessage(f"[Output] Error during file conversion for {zonename}")
                                skipsim = True
                                continue
                        else:
                            log_message(filelog, "INFO",
                                        f"Simulation skipped zone {str(point[1])}, results already exist (existing results merged)")
                            messages.addMessage(f"Simulation skipped zone {str(point[1])}, results already exist (existing results merged)")

                        # Raster processing and summary
                        try:
                            if not arcpy.Exists(currentresult):
                                try:
                                    arcpy.Copy_management(currentsimfolder + "\\elev_" + "zone"+str(point[1]) + ".tif", currentresult)
                                except Exception as e:
                                    log_message(filelog, "ERROR", f"Failed to create initial result raster for {currentresult}: {str(e)}")
                                    messages.addErrorMessage(f"[Output] Failed to create result raster: {str(e)}")
                                    skipsim = True
                            else:
                                try:
                                    arcpy.Mosaic_management(currentsimfolder + "\\elev_" + "zone"+str(point[1]) + ".tif", currentresult, mosaic_type="MAXIMUM")
                                except Exception as e:
                                    log_message(filelog, "ERROR", f"Failed to mosaic elevation raster for zone {point[1]}: {str(e)}")
                                    messages.addErrorMessage(f"[Output] Failed to mosaic raster for zone {point[1]}: {str(e)}")
                                    skipsim = True

                        except BaseException as e:
                            error_type = type(e).__name__
                            error_msg = f"CRITICAL ERROR in {simname}: simulation aborted during zone {point[1]}\nError Type: {error_type}\nError Message: {str(e)}"
                            log_message(filelog, "ERROR", error_msg)
                            filelog.write(repr(e) + "\n")
                            filelog.write("=" * 80 + "\n")
                            messages.addErrorMessage(f"[Critical] {error_msg}")
                            messages.addWarningMessage("Some simulations skipped. See log file for details.")
                            skipsim = True

    # Summary and cleanup
    log_message(filelog, "INFO", "=" * 80)
    log_message(filelog, "INFO", "SIMULATION EXECUTION COMPLETED")
    log_message(filelog, "INFO", "=" * 80)

    try:
        filelog.close()
        log_file_size = os.path.getsize(str_log) / 1024  # Size in KB
        print(f"Log file written: {str_log} ({log_file_size:.1f} KB)")
    except Exception as e:
        messages.addWarningMessage(f"Could not properly close log file: {str(e)}")

    return