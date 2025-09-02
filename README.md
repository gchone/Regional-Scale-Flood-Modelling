# Large-Scale Flood Modelling Tools

These tools implement the large-scale flood modelling process described in:

* **Choné, G., Biron, P.M., Buffin-Bélanger, T., Mazgareanu, I., Neal, J.C., and Sampson, C.C.** (2021). *An assessment of large-scale flood modelling based on LiDAR data.* Hydrological Processes, 35(8), e14333. [https://doi.org/10.1002/hyp.14333](https://doi.org/10.1002/hyp.14333)

* **Choné, G., Mazgareanu, I., Biron, P.M., Buffin-Bélanger, T., Larouche-Tremblay, F., Perry, B., and Fortin, M.** (2024). *Large-scale flood modelling based on LiDAR data: a case study in the Southwest Miramichi watershed, New Brunswick, Canada.* Canadian Water Resources Journal, 1–19. [https://doi.org/10.1080/07011784.2024.2430776](https://doi.org/10.1080/07011784.2024.2430776)

These tools include the bed assessment procedure, integrated with ArcGIS tools and data structures to support the development of large-scale hydraulic models from LiDAR data.
A stand-alone version of the bed assessment procedure (not requiring ArcGIS) is available in the repository [ConcordiaRiverLab-BedAssessment](https://github.com/gchone/ConcordiaRiverLab-BedAssessment).

---

## Branches and Releases

* The main branch, "ArcGIS", contains the latest version of the tools. A zip file is available in the [Releases](https://github.com/gchone/ConcordiaRiverLab-FloodTools/releases) section.
* The "OpenGIS" branch is an ongoing effort to convert the tools to open-source GIS libraries (e.g., GDAL).
  ⚠️ *Note: This branch is not functional as of June 2025.*

---

## Requirements

* **ArcGIS Pro** with an **Advanced license** and the **Spatial Analyst extension**.
  The **3D Analyst extension** is optional but may be helpful.
* **LISFLOOD-FP** version 7 or above
  [Bristol University LISFLOOD-FP](http://www.bristol.ac.uk/geography/research/hydrology/models/lisflood/)
  [Zenodo Archive](https://zenodo.org/record/4073011#.ZCbhlXbMKUl)
* **LAStools** by rapidlasso GmbH
  [https://rapidlasso.com/lastools](https://rapidlasso.com/lastools)

---

## Installation

To install the tools:

1. Open ArcGIS Pro.
2. In the **Catalog** window, browse to the folder containing the tools.
3. Two geoprocessing toolboxes should appear automatically and be ready for use.

---

## Documentation

Step-by-step instructions are provided in the file:
**`Documentation_ConcordiaRiverLabTools2021_vNRCan3.2.1.docx`**

