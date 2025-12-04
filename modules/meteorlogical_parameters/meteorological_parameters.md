# Integrating Meteorological Data into FDS

To accurately simulate the flow domain in FDS, it's essential to provide realistic meteorological parameters, particularly temperature and velocity profiles, which are crucial for driving turbulence and atmospheric stability.
## Data Sources

The preferred method is to use in-situ instrument measurements (e.g., weather station data) and input these parameters directly into the FDS input file.

However, in the absence of direct measurements, we rely on the ERA5 hourly averaged datasets provided by the Copernicus Climate Change Service (C3S) to derive the necessary atmospheric boundary layer conditions for the simulation. It is highly recommended to download the data in NetCDF (.nc) format, as this is a standard format that is easy to process and integrate with Python libraries like netCDF4 (as seen in the terrain generation process).

##  Required ERA5 Parameters

ERA5 data is organized into two main dataset types, and we need specific variables from both:

### 1. Surface Levels (Single Levels)

These parameters provide boundary conditions and near-surface profiles:
| Parameters | FDS Relevance |	
| :---: | :--- |
|10 m u&v component of wind	| Defines horizontal wind speed and direction at 10 m.|
|100 m u&v component of wind	| Defines horizontal wind speed and direction at 100 m.|
|2 m Temperature	| Defines the air temperature near the ground.|
| Skin Temperature (Tground​)	| Defines the ground surface temperature, important for heat transfer.|
| Surface Pressure	| Used to calculate atmospheric density and stability.|

Download Link: [ERA5 Single Levels](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download)

### 2. Pressure Levels

These parameters are essential for constructing a vertical profile of the atmosphere above the surface:
| Parameters | FDS Relevance |	
| :---: | :--- |
| Velocity Profiles (u and v)	| Defines wind speed and direction at different pressure altitudes. |
| Temperature Profiles (T)	| Defines air temperature at different pressure altitudes. |

Download Link: [ERA5 Pressure Levels](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels?tab=overview)
