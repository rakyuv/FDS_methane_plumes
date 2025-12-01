# 🗺️ DTM/LiDAR to FDS Input File Conversion Guide

This guide outlines the process of downloading Digital Terrain Model (DTM) LiDAR data in `.las` format, preprocessing it, and converting it into files suitable for use with Fire Dynamics Simulator (FDS), typically by generating raster files (TIFF/NetCDF).

---

## 1. Download DTM LAS Files (Example: France)

The first step is to download the DTM LiDAR file in `.las` or compressed `.laz` format. The process is country-specific; the method for France is detailed below:

* **Visit the IGN GeoServices website:** Navigate to the official IGN LiDAR HD page:
    * <https://geoservices.ign.fr/lidarhd>
* **Access the Download Interface:** Go to the **"Interfaces de téléchargement"** tab.
* Click the link labeled **"Interface de téléchargement des Nuages de points LiDAR HD"**.
* Download the necessary `.laz` files corresponding to your area of interest.

---

## 2. Preprocessing LAS/LAZ Files (Merging and Cropping)

LiDAR datasets are often tiled, meaning your area of interest may span multiple large files or be contained within a much larger tile. Preprocessing involves merging adjacent files and then cropping to the specific region you need.

### 2.1. Merging Datasets (LAStools)

To combine adjacent `.laz` files, you need to install **LAStools**.

* **Install LAStools:** Download the necessary tools from the official website.
* **Merge Command:** Use `lasmerge` to combine the files.

**Code Snippet:**
```command-line
lasmerge -i input_file1.laz input_file2.laz -o merged_output.laz
```
### 2.2. Cropping the Area of Interest (PDAL)

While LAStools offers a cropping utility (lasclip), it may not be free access. PDAL (Point Data Abstraction Library) is an effective, free alternative for cropping based on spatial bounds.

You will need to create a JSON pipeline file to define the cropping operation.

* Crop Pipeline (crop_pipeline.json):

**Code Snippet:**
```JSON
  "pipeline": [
    {
      "type": "readers.las",
      "filename": "input.laz"
    },
    {
      "type": "filters.crop",
      "bounds": "([xmin, xmax], [ymin, ymax])"
    },
    {
      "type": "writers.las",
      "filename": "cropped_output.laz"
    }
  ]
}
```
Note: Replace ([xmin, xmax], [ymin, ymax]) with the actual geographic coordinates defining your area of interest.

Execute the Pipeline: Run the PDAL command in your terminal:

**Code snippet:**
```command-line
pdal pipeline crop_pipeline.json
```

## 3. Filtering and Classification (LAStools)

LiDAR files often contain multiple layers (classes) of points (ground, buildings, vegetation, etc.). It is necessary to filter the specific classes required for your FDS model.

You can verify the class layer numbers by opening the .laz file in a GIS tool like QGIS. Use the las2las64 utility from LAStools to filter the data.

---

| Class ID | Description |	Example Command |
| 2 |	Ground |	las2las64 -i cropped_output.laz -o ground.laz -keep_class 2
| 6 |	Building |	las2las64 -i cropped_output.laz -o building.laz -keep_class 6
| 5 |	Tall Vegetation	|las2las64 -i cropped_output.laz -o vegetation_tall.laz -keep_class 5
| 2 & 6 |	Ground & Buildings |	las2las64 -i cropped_output.laz -o ground_building.laz -keep_class 2 -keep_class 6

---

4. Converting LAZ to TIFF (PDAL)

The next step is to convert the filtered point cloud (.laz) into a raster image (.tif), specifically a Digital Surface Model (DSM) or Digital Elevation Model (DEM). This uses the PDAL writers.gdal driver.

* Conversion Pipeline (pipeline.json):

**Code Snippet:**
```JSON

{
  "pipeline": [
    {
      "type": "readers.las",
      "filename": "input.laz"
    },
    {
      "type": "writers.gdal",
      "filename": "output_dsm.tif",
      "resolution": 1.0,
      "data_type": "float32",
      "output_type": "idw"
    }
  ]
}
```
Note: This example uses a 1.0m resolution and the Inverse Distance Weighting (IDW) method to interpolate the raster values from the point cloud.

* Execute the Conversion:

**Code snippet**
```command-line
pdal pipeline pipeline.json
```

The resulting output_dsm.tif is your initial raster file.

## 5. Final Resampling and Format Conversion (GDAL)

The final steps involve adjusting the raster resolution and converting the format, if necessary.

### 5.1. Resampling/Undersampling TIFF (gdalwarp)

If a coarser resolution is required, use gdalwarp with the target resolution (-tr) flag.
Code snippet

**Code snippet**
```command-line
gdalwarp -tr <x_res> <y_res> -r <resampling_method> <input_file.tif> <output_file.tif>
```

### 5.2. Converting to NetCDF (gdal_translate)

FDS may prefer or require input files in the NetCDF (.nc) format. Use gdal_translate for this final conversion.
Code snippet

**Code snippet**
``` command-line
gdal_translate -of NETCDF <input_file.tif> <output_file.nc>
```
