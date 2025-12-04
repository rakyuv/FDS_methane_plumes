## 1. Reproject to a Metric Coordinate System for FDS

FDS requires elevation input to be in a metric coordinate system (units in meters), not the angular (Lat/Lon) WGS84 system. Use gdalwarp for this reprojection.

  * s_srs (Source SRS): The current SRS of cropped.tif (e.g., EPSG:4326 for WGS 84).

  * t_srs (Target SRS): The desired metric projection (e.g., a UTM Zone).

  * -r bilinear: Uses bilinear interpolation for smoother elevation data.

```command-line
gdalwarp -overwrite -s_srs EPSG:source -t_srs EPSG:target -r bilinear -of GTiff cropped.tif output_dem.tif
```
  **Important**: You must find the correct Target EPSG code for the specific location of your area (usually a UTM Zone). Use the EPSG Registry website for look-up.

The resulting file, `output_dem.tif`, is the metric elevation map ready to be input into FDS.

### 2. Converting to NetCDF (gdal_translate)

FDS may prefer or require input files in the NetCDF (`.nc`) format. Use gdal_translate for this final conversion.
Code snippet

``` command-line
gdal_translate -of NETCDF <input_file.tif> <output_file.nc>
```
