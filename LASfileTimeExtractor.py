import subprocess
import os
import datetime
import time
#import csv
#from tqdm import tqdm



def execute_extract_bydays(str_binlastoolsfolder, str_lasfolder, UTC, output_folder, merge_folder, messages):

    messages.addMessage("Filtering las files by days...")

    donefiles = set()
    for r, d, f in os.walk(output_folder):
        for file in f:
            donefiles.add(file[:-4])


    #filecsv = open(output_csv, 'w')
    #filecsv.write("file,min_time,max_time\n")
    gps_epoch = datetime.datetime(1980, 1, 6)
    files = []
    # r=root, d=directories, f = files
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

                min_day = min_real_time.date()
                max_day = max_real_time.date()
                day = min_day
                while day <= max_day:
                    if not os.path.exists(os.path.join(output_folder, str(day))):
                        os.makedirs(os.path.join(output_folder, str(day)))
                    gps_time1 = (datetime.datetime(day.year, day.month, day.day) - gps_epoch).total_seconds() - 1000000000 - UTC*3600
                    gps_time2 = gps_time1 + 24*3600

                    las2las_cmd = [str_binlastoolsfolder + "\\las2las.exe", "-i", file, "-o", os.path.join(output_folder, str(day), file[:-4]+".las"),
                                          "-keep_class", "2",
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
            p = subprocess.Popen([str_binlastoolsfolder + "\\lasinfo.exe", file], cwd=r,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            out, err = p.communicate()
            nb_points = 0
            for elem in str(err).split(r"\r\n"):
                if elem.find("number of point records") > -1 and not (elem.find("extended number of point records") > -1):
                    subelem = elem.strip().split()
                    nb_points = nb_points + int(subelem[4])
                if elem.find("extended number of point records") > -1:
                    subelem = elem.strip().split()
                    nb_points = nb_points + int(subelem[5])
            if nb_points == 0: #empty las file
                if os.path.exists(os.path.join(r, file)):
                    os.remove(os.path.join(r, file))


    for r, d, f in os.walk(output_folder):
        if len(f) == 0 and len(d)==0: # empty root directory
            os.rmdir(r)

    messages.addMessage("Merging tiles by days")

    for r, d, f in os.walk(output_folder):
        for dir in d:
            p = subprocess.Popen([str_binlastoolsfolder + "\\lasmerge.exe", "-i", os.path.join(r, dir,"*.las"), "-o",
                                  os.path.join(merge_folder, "lidar"+dir+ ".las")], cwd=output_folder,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            out, err = p.communicate() # make the script wait for the lasmerge to be done

    messages.addMessage("Computing footprints")
    p = subprocess.Popen([str_binlastoolsfolder + "\\lasboundary.exe", "-i", os.path.join(merge_folder, "*.las")], cwd=merge_folder,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    out, err = p.communicate()  # make the script wait for the lasboundary to be done
