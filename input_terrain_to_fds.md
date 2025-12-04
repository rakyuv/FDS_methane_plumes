### 5.2. Converting to NetCDF (gdal_translate)

FDS may prefer or require input files in the NetCDF (`.nc`) format. Use gdal_translate for this final conversion.
Code snippet

``` command-line
gdal_translate -of NETCDF <input_file.tif> <output_file.nc>
```
