# Generating FDS Terrain Input from DEM Data

This document outlines the final steps for preparing Digital Elevation Model (DEM) data for use as terrain input in a Fire Dynamics Simulator (FDS) input file using the `&OBST` name list.

The input process supports data from various sources, including:

   * SRTM1: Global 30-meter resolution DEM. (Refer to [this file](srtm1_to_tif.md) for download and conversion steps).

   * LiDAR: High-resolution datasets available in certain areas. (Refer to [this file](lasfiles_to_tif.md) for conversion steps).

The core requirement for FDS is that the elevation data must be in a metric coordinate system.
## 1. Reprojecting to a Metric Coordinate System (GDAL)

The raw DEM data is usually in the angular (Lat/Lon) WGS84 system. FDS requires units in meters. The `gdalwarp` utility is used to perform this spatial reprojection.

```command-line
gdalwarp -overwrite -s_srs EPSG:source -t_srs EPSG:target -r bilinear -of GTiff cropped.tif output_dem.tif
```
| Parameter	 | Description |	Example Value |
| :---: | :--- | :--- |
| s_srs | (Source SRS)	| The current spatial reference system of the input file.	EPSG:4326 (WGS 84) |
| t_srs | (Target SRS)	| The required metric projection for your location (e.g., a UTM Zone).	EPSG:32634 (WGS 84 / UTM zone 34N) |
| -r | bilinear |	Uses bilinear interpolation for resampling, which results in smoother elevation data.	|

**Important**: You must find the correct Target EPSG code for the specific geographic location of your area (usually a UTM Zone). Use the [EPSG Registry](https://epsg.io) for look-up.

## 2. Converting TIFF to NetCDF Format (GDAL)

FDS may prefer or require input files in the NetCDF (`.nc`) format. Use the `gdal_translate` utility for this final conversion.

```command-line
gdal_translate -of NETCDF output_dem.tif output_file.nc
```
The resulting file, `output_file.nc`, is the metric elevation map ready to be processed for FDS input. Make sure to rename this file following the resolution pattern (e.g., `terrain_30m.nc`) if you use the multi-resolution Python script below.

## 3. Python Script: Generating FDS &OBST Cards

If your FDS domain uses a single resolution, you need one `output_file.nc`. For simulations with multiple grid resolutions (highest resolution near the source, diminishing outward), you will need a NetCDF file corresponding to each resolution (e.g., `terrain_1m.nc`, `terrain_3m.nc`).

The following Python script reads the NetCDF data, handles multiple resolution zones, and outputs the terrain definition directly as `&OBST` name lists into a `terrain.fds` file.

```Python
import numpy as np
from netCDF4 import Dataset

def write_terrain(x, y, z, zmin, terrain_limit_l, terrain_limit_u, file_handle):
    """
    Writes terrain data as FDS &OBST cards to a file.

    Args:
        x (np.array): Array of x-coordinates (centered).
        y (np.array): Array of y-coordinates (centered).
        z (np.array): 2D array of z-coordinates (terrain elevation).
        zmin (float): The minimum elevation for the terrain.
        terrain_limit_l (float): Lower limit for the terrain-defining square (inner boundary).
        terrain_limit_u (float): Upper limit for the terrain-defining square (outer boundary).
        file_handle: The file handle to write to.
    """
    resolution_local = x[1] - x[0]

    # Print a header for the new terrain section
    print(f"\nTerrain {resolution_local:.2f} m", file=file_handle)
    
    for i in range(len(x) - 1):
        for j in range(len(y) - 1):
            
            x_val = x[i]
            y_val = y[j]
            
            # Condition 1: Must be within the outer limit (or no outer limit defined)
            is_within_outer_square = (terrain_limit_u is None) or \
                                     (abs(x_val) < terrain_limit_u and abs(y_val) < terrain_limit_u)

            # Condition 2: Must be outside the inner limit (or no inner limit defined)
            is_outside_inner_square = (terrain_limit_l is None) or \
                                      (abs(x_val) >= terrain_limit_l or abs(y_val) >= terrain_limit_l)

            if is_within_outer_square and is_outside_inner_square:
                # The &OBST card defines a solid block from Z=zmin up to the terrain elevation z[j,i]
                print(f"&OBST XB={x[i]:.2f},{x[i+1]:.2f},{y[j]:.2f},{y[j+1]:.2f},{zmin:.2f},{z[j,i]:.2f}/", file=file_handle)

def read_terrain_files(resolution):
    """
    Reads and pre-processes terrain data from a NetCDF file.
    
    Args:
        resolution (int): The resolution in meters (e.g., 1, 3, 30).
    
    Returns:
        tuple: x, y, z, and zmin numpy arrays.
    """
    # *** UPDATED FILE NAMING ***
    inputFile = f'terrain_{resolution}m.nc' 
    
    # Example source coordinates to center the grid (UTM Easting, Northing)
    source = np.array([767813.002, 5542589.380]) 
    
    with Dataset(inputFile, 'r') as ncfile:
        x = np.array(ncfile.variables['x'][:]).squeeze()
        y = np.array(ncfile.variables['y'][:]).squeeze()
        z = np.array(ncfile.variables['Band1'][:, :]).squeeze()

    # Center the coordinates relative to the source
    x = x - source[0]
    y = y - source[1]

    # Rounding for FDS input precision
    x = np.round(x, 2)
    y = np.round(y, 2)
    z = np.round(z, 2)
    
    # Calculate the minimum elevation (excluding potentially bad data points)
    zmin = np.min(z[z != np.min(z)])
    # Set all elevations below this calculated minimum to zmin
    z[z < zmin] = zmin
    
    return x, y, z, zmin

if __name__ == '__main__':
    output_filename = 'terrain.fds'

    with open(output_filename, 'w') as file_handle:
        print("&HEAD CHID='TERRAIN_INPUT', TITLE='Terrain Obstacles' /", file=file_handle)
        print("Starting terrain generation...", file=file_handle)
        
        # Define resolution cases for the multi-resolution domain
        # Ensure you have files named terrain_30m.nc, terrain_10m.nc, etc.
        resolution_cases = [
            {'resolution': 30, 'lower_limit': 400, 'upper_limit': None}, # Outermost ring
            {'resolution': 10, 'lower_limit': 130, 'upper_limit': 420}, # Middle ring
            {'resolution': 5, 'lower_limit': 44, 'upper_limit': 140},   # Inner ring
            {'resolution': 2, 'lower_limit': None, 'upper_limit': 48},  # Center zone (highest resolution)
        ]
        
        combined_zmin = np.inf
        mock_data = {}

        # First pass to find the true lowest elevation across all files
        for case in resolution_cases:
            res = case['resolution']
            try:
                x, y, z, zmin = read_terrain_files(res)
                combined_zmin = min(combined_zmin, zmin)
                mock_data[res] = {'x': x, 'y': y, 'z': z}
            except FileNotFoundError:
                print(f"Error: terrain_{res}m.nc not found. Skipping this resolution.", file=file_handle)

        # Second pass to write the FDS cards using the globally consistent zmin
        for case in resolution_cases:
            res = case['resolution']
            if res in mock_data:
                data = mock_data[res]
                write_terrain(data['x'], data['y'], data['z'], combined_zmin, case['lower_limit'], case['upper_limit'], file_handle)

        print("\nTerrain generation complete. Check 'terrain.fds' for output.", file=file_handle)
```
Save the code above as a Python file (e.g., `generate_terrain_fds.py`) and run it to create the `terrain.fds` file, which can then be included in your main FDS input file.
