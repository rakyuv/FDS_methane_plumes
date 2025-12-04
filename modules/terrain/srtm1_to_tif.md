# Preparing SRTM1 Elevation Data for FDS Input

This guide details the process of downloading and converting SRTM1 Digital Elevation Model (DEM) data into a TIFF file, which can then be used as topographic input for a Fire Dynamics Simulator (FDS) model.

The key steps involve using the Python `elevation` package, followed by the GDAL (Geospatial Data Abstraction Library) utility tools (`gdalbuildvrt`, `gdal_translate`, and `gdalwarp`).

## 1. Download Elevation Data using elevation

First, ensure you have the `elevation` package installed in your Python environment:

```Bash
  pip install elevation
```

The `elevation` command-line utility, `eio`, is used to clip and download the necessary SRTM1 tiles based on bounding box coordinates. It automatically handles fetching data.

  * Coordinates: The example below is centered near 49.975∘N,18.735∘E and defines a bounding box large enough to cover the area of interest.

  * Bounding Box Format: The format is `min_lon min_lat max_lon max_lat`.


```command-line
  eio clip -o input_elevation.tif --bounds 17.7352082214116 48.97526012838302 19.7352082214116 50.97526012838302
```
   **Note**: The individual SRTM1 data files are cached locally, typically in a directory like `/Users/*user*/Library/Caches/elevation/SRTM1/cache/`. This command may download two or more files.


## 2. Merge Downloaded Tiles (If Necessary)

If the area of interest spans multiple SRTM tiles (e.g., `N49E018`, `N50E018`), you need to merge the cached files using `gdalbuildvrt`. This tool creates a Virtual Raster Tile (`.vrt`) file, which links the individual files together as a single source without physically duplicating the data.

```command-line
gdalbuildvrt merged.vrt N49E018.tif N50E018.tif
```
  **Tip**: You usually run this command from the cache directory or provide the full paths to the `.tif` files.

## 3. Crop the Area of Interest

The downloaded or merged file is usually larger than your simulation domain. Use `gdal_translate` with the `-projwin` option to crop the file precisely to your boundaries.

  * Input: The `merged.vrt` file.

  * Output: `cropped.tif`
    
  *  -projwin Format: `upper_left_lon upper_left_lat lower_right_lon lower_right_lat`. 


These coordinates must be in the input file's spatial reference system (Lat/Lon).

```command-line
gdal_translate -projwin 18.67933600352784 50.011231351404604 18.79108043929536 49.93928890536144 merged.vrt cropped.tif
```

