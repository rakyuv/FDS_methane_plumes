# Integrating Meteorological Data into FDS

To accurately simulate the flow domain in FDS, it's essential to provide realistic meteorological parameters, particularly temperature and velocity profiles, which are crucial for driving turbulence and atmospheric stability.

## Data Sources

The preferred method is to use in-situ instrument measurements (e.g., weather station data) and input these parameters directly into the FDS input file.

However, in the absence of direct measurements, we rely on the ERA5 hourly averaged datasets provided by the Copernicus Climate Change Service (C3S) to derive the necessary atmospheric boundary layer conditions for the simulation. It is highly recommended to download the data in NetCDF (.nc) format, as this is a standard format that is easy to process and integrate with Python libraries like netCDF4 (as seen in the terrain generation process).

## Required ERA5 Parameters

ERA5 data is organized into two main dataset types, and we need specific variables from both:

### 1. Surface Levels (Single Levels)

These parameters provide boundary conditions and near-surface profiles:

| Parameters | FDS Relevance |
| :---: | :--- |
| 10 m u & v component of wind | Defines horizontal wind speed and direction at 10 m. |
| 100 m u & v component of wind | Defines horizontal wind speed and direction at 100 m. |
| 2 m Temperature | Defines the air temperature near the ground. |
| Skin Temperature (T_ground) | Defines the ground surface temperature, important for heat transfer. |
| Surface Pressure | Used to calculate atmospheric density and stability. |
| 2 m Dewpoint Temperature | Used for humidity and stability calculations. |
| Mean Sea Level Pressure | Provides synoptic-scale pressure field. |
| Total Precipitation | Contextual atmospheric condition. |
| Soil Temperature Level 1 | Near-surface soil thermal state. |
| High/Low Vegetation Cover | Surface roughness and land-use context. |
| Boundary Layer Height | Defines the depth of the turbulent mixing layer. |

Download Link: [ERA5 Single Levels](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download)

### 2. Pressure Levels

These parameters are essential for constructing a vertical profile of the atmosphere above the surface. All 37 standard ERA5 pressure levels are used (1–1000 hPa), covering the full atmospheric column from the near-surface up to ~48 km:

| Parameters | FDS Relevance |
| :---: | :--- |
| Velocity Profiles (u and v) | Defines wind speed and direction at different pressure altitudes. |
| Temperature Profiles (T) | Defines air temperature at different pressure altitudes. |
| Geopotential (z) | Converts pressure levels to geometric altitudes above MSL. |
| Specific Humidity | Atmospheric moisture content at each level. |
| Relative Humidity | Contextual stability and moisture information. |

Download Link: [ERA5 Pressure Levels](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels?tab=overview)

## Automated Download: `era5_downloader.py`

The script `era5_downloader.py` automates the retrieval and processing of both dataset types for a specified location and timestamp via the [CDS API](https://cds.climate.copernicus.eu/api-how-to).

### Requirements

```bash
pip install cdsapi xarray netCDF4 numpy
```

A valid CDS API key file must exist at `~/.cdsapirc`:

```
url: https://cds.climate.copernicus.eu/api/v2
key: YOUR-UID:YOUR-API-KEY
```

### Outputs

| File | Contents |
| :--- | :--- |
| `era5_single_levels.nc` | All single-level variables as a NetCDF file |
| `era5_pressure_levels.nc` | All pressure-level variables as a NetCDF file |
| `era5_fds_ramp_<DATE>_<HH>UTC.txt` | FDS-ready `&WIND` and `&RAMP` namelists |

### FDS RAMP Profile Format

The pressure-level data is processed into FDS `&RAMP` namelists ready to paste directly into an FDS input file. Geopotential at each pressure level is converted to geometric altitude (m above MSL) using:

$$z_{\text{geom}} = \frac{R_e \cdot z_{\text{gp}}}{R_e - z_{\text{gp}}}, \quad z_{\text{gp}} = \frac{\Phi}{g_0}$$

where $R_e = 6{,}356{,}766$ m and $g_0 = 9.80665$ m s⁻².

The output file contains two profile types:

- **Wind speed profile** (`RAMP ID='spd'`): scalar wind speed $\sqrt{u^2 + v^2}$ at each geometric altitude.
- **Temperature profile** (`RAMP ID='T profile'`): dimensionless ratio $T(z)\,/\,T_{\text{2m}}$ (both in Kelvin), anchored to 1.0 at the surface.

Example output:

```
&WIND SPEED=7.43., RAMP_SPEED_Z='spd', RAMP_TMP0_Z='T profile', DIRECTION=214.3/
!
! ERA5 Velocities
&RAMP ID='spd', Z=111.23, F=4.21/
&RAMP ID='spd', Z=287.54, F=5.88/
...
! ERA5 Temperature Ratios  (T(z) / T_2m)
&RAMP ID='T profile', Z=111.23, F=0.99/
&RAMP ID='T profile', Z=287.54, F=0.98/
...
```

### Usage — Standalone

Edit the parameter block at the top of the script and run directly:

```python
# era5_downloader.py — USER PARAMETERS
LAT     =  48.8566    # decimal degrees (positive = North)
LON     =   2.3522    # decimal degrees (positive = East)
DATE    = "2023-07-15"  # YYYY-MM-DD
HOUR    =  12           # UTC hour, integer 0–23
OUT_DIR = "."           # output folder (created if absent)
```

```bash
python era5_downloader.py
```

### Usage — As an Imported Module

The script exposes a `run()` function so that any other script can fetch the outputs by simply passing the required parameters:

```python
from era5_downloader import run

result = run(
    lat     = 48.8566,
    lon     =  2.3522,
    date    = "2023-07-15",
    hour    = 12,
    out_dir = "./outputs",
)

# result keys:
#   result["netcdf_single"]    → path to era5_single_levels.nc
#   result["netcdf_pressure"]  → path to era5_pressure_levels.nc
#   result["ramp_txt"]         → path to FDS RAMP text file
```

`run()` returns a dictionary of absolute file paths, which the calling script can immediately use to open the NetCDF files with `xarray` / `netCDF4`, or to locate the RAMP text file for injection into an FDS input deck.
