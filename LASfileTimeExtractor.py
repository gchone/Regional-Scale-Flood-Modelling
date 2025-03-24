import subprocess
import os
import datetime
import time
#import csv
#from tqdm import tqdm



def execute_extract_bydays(str_binlastoolsfolder, str_lasfolder, UTC, output_folder, ground_folder, merge_folder, messages):

    messages.addMessage("Filtering las files by days...")

    # Skip already process files (the ones already in the output folder)
    donefiles = set()
    for r, d, f in os.walk(output_folder):
        for file in f:
            donefiles.add(file[:-4])


    #filecsv = open(output_csv, 'w')
    #filecsv.write("file,min_time,max_time\n")
    gps_epoch = datetime.datetime(1980, 1, 6)
    files = []
    # r=root, d=directories, f = files

    # Scan through the files with lasinfo in order to find the time of the first and last point acquired in the las file
    for r, d, f in os.walk(str_lasfolder):
        for file in f:
            if (file[-4:] == '.laz' or file[-4:] == '.las') and file[:-4] not in donefiles:
                p = subprocess.Popen([str_binlastoolsfolder + "\\lasinfo.exe", file], cwd=str_lasfolder, stdout=subprocess.PIPE,  stderr=subprocess.PIPE, shell=True)
                out, err = p.communicate()
                for elem in str(err).split(r"\r\n"):
                    if(elem.find("gps_time")) > -1:
                        subelem= elem.strip().split()
                        min_gpstime = int(subelem[1].split('.')[0]) + 1000000000
                        max_gpstime = int(subelem[2].split('.')[0]) + 1000000000

                local_min = min_gpstime + UTC*3600
                local_max = max_gpstime + UTC*3600

                min_real_time = gps_epoch + datetime.timedelta(seconds=local_min)
                max_real_time = gps_epoch + datetime.timedelta(seconds=local_max)
                #min_real_time = max(min_real_time, datetime.datetime(2019, 7, 1)) #!! Temp fix for Shubi 2019

                min_day = min_real_time.date()
                max_day = max_real_time.date()
                day = min_day

                # Create a las file for each day between the first and the last point acquired in the las file
                while day <= max_day:
                    if not os.path.exists(os.path.join(output_folder, str(day))):
                        os.makedirs(os.path.join(output_folder, str(day)))
                    gps_time1 = (datetime.datetime(day.year, day.month, day.day) - gps_epoch).total_seconds() - 1000000000 - UTC*3600
                    gps_time2 = gps_time1 + 24*3600
                    las2las_cmd = [str_binlastoolsfolder + "\\las2las.exe", "-i", file, "-o", os.path.join(output_folder, str(day), file[:-4]+".las"),
                                          #"-keep_class", "2", "-keep_class", "9", "-keep_class", "1", "-keep_class", "10", "-keep_class", "11",
                                          "-keep_gps_time", str(gps_time1), str(gps_time2)]

                    p = subprocess.Popen(las2las_cmd, cwd=str_lasfolder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                    out, err = p.communicate()  # make the script wait for the las2las to be done

                    day = day + datetime.timedelta(days=1)

                #filecsv.write(file+","+str(min_real_time)+","+str(max_real_time)+"\n")
                #print(file+": done")
    #filecsv.close()

    messages.addMessage("Cleaning out empty las files...")

    for r, d, f in os.walk(output_folder):
        for file in f:
            file_size = os.path.getsize(os.path.join(r, file))
            if file_size / (1024 * 1024) < 1:  # check only files of less than 1 MB
                p = subprocess.Popen([str_binlastoolsfolder + "\\lasinfo.exe", file], cwd=r,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                out, err = p.communicate()
                nb_points = 0
                points_checked = False
                for elem in str(err).split(r"\r\n"):
                    if elem.find("number of point records") > -1 and not (elem.find("extended number of point records") > -1):
                        subelem = elem.strip().split()
                        nb_points = nb_points + int(subelem[4])
                        points_checked = True
                    if elem.find("extended number of point records") > -1:
                        subelem = elem.strip().split()
                        nb_points = nb_points + int(subelem[5])
                        points_checked = True
                if not points_checked:
                    raise Exception("Error checking points count: " + os.path.join(r, file))
                    exit()
                if nb_points == 0: #empty las file
                    if os.path.exists(os.path.join(r, file)):
                        os.remove(os.path.join(r, file))


    for r, d, f in os.walk(output_folder):
        if len(f) == 0 and len(d)==0: # empty root directory
            os.rmdir(r)

    messages.addMessage("Ground classification")

    for r, d, f in os.walk(output_folder):
        for dir in d:
            if not os.path.exists(os.path.join(ground_folder, dir)):
                os.makedirs(os.path.join(ground_folder, dir))
            p = subprocess.Popen([str_binlastoolsfolder + "\\lasground_new64.exe", "-i", os.path.join(r, dir,"*.las"), "-odir",
                                  os.path.join(ground_folder, dir)], cwd=output_folder,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            out, err = p.communicate() # make the script wait for the lasground to be done


    messages.addMessage("Merging tiles by days + Ground filtering")

    for r, d, f in os.walk(ground_folder):
        for dir in d:
            p = subprocess.Popen([str_binlastoolsfolder + "\\lasmerge.exe", "-keep_class", "2", "-i", os.path.join(r, dir,"*.las"), "-o",
                                  os.path.join(merge_folder, "lidar"+dir+ ".las")], cwd=ground_folder,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            out, err = p.communicate() # make the script wait for the lasmerge to be done

    messages.addMessage("Computing footprints")
    p = subprocess.Popen([str_binlastoolsfolder + "\\lasboundary.exe", "-i", os.path.join(merge_folder, "*.las")], cwd=merge_folder,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    out, err = p.communicate()  # make the script wait for the lasboundary to be done