# era5_downloader.py

Downloads ERA5 reanalysis data for a given location and timestamp, and
converts it into FDS-ready wind and temperature profiles. Designed to be
used either as a standalone script or imported as a module by `build_fds.py`.

---

## What it downloads

Two CDS API requests are made, both clipped to a 0.25° box around the target
point:

| Request | Variables | Output |
|---|---|---|
| Single-level reanalysis | 2 m temperature, 2 m dewpoint, 10 m U/V wind, surface pressure, skin temperature | `era5_single_levels.nc` |
| Pressure-level reanalysis | U wind, V wind, temperature, geopotential | `era5_pressure_levels.nc` |

From these two files a third output is derived:

| Output | Description |
|---|---|
| `era5_fds_ramp_<YYYY-MM-DD>_<HH>UTC.txt` | FDS `&WIND` and `&RAMP` namelists ready to paste or include in an FDS input file |

All files are written to the current working directory.

---

## Requirements

```bash
pip install cdsapi xarray netCDF4 numpy
```

A valid `~/.cdsapirc` file is required with your Copernicus CDS API key:

```
url: https://cds.climate.copernicus.eu/api/v2
key: <your-uid>:<your-api-key>
```

Register and obtain a key at: https://cds.climate.copernicus.eu

---

## Usage

### As a standalone script

Edit the `USER PARAMETERS` block at the top of the file, then run:

```bash
python era5_downloader.py
```

### As an imported module

```python
from era5_downloader import run

result = run(
    lat   = 49.583,
    lon   = 18.441,
    date  = "2024-06-01",
    hour  = 12,
    z_min = 247.0,
)

# result is a dict:
# {
#   "ramp_txt"     : "era5_fds_ramp_2024-06-01_12UTC.txt",
#   "t2m"          : 293.15,   # K  → used as TMPA in &MISC
#   "skin_temp"    : 298.40,   # K  → used as TMP_FRONT in &SURF
#   "surface_pres" : 97800.0,  # Pa → used as P_INF in &MISC
# }
```

---

## Parameters

| Parameter | Type | Description |
|---|---|---|
| `lat` | `float` | Latitude of the point of interest in decimal degrees (positive = North) |
| `lon` | `float` | Longitude of the point of interest in decimal degrees (positive = East) |
| `date` | `str` | Date in `YYYY-MM-DD` format |
| `hour` | `int` | UTC hour, integer 0–23 |
| `z_min` | `float` | Lowest Z coordinate of the FDS domain in metres above sea level. Used to anchor the 10 m wind point at `z_min + 10`. Defaults to `0.0` |

---

## Returned values

The `run()` function returns a dict with the following keys:

| Key | Unit | FDS use |
|---|---|---|
| `ramp_txt` | — | Path to the generated RAMP file |
| `t2m` | K | 2 m air temperature → `TMPA` in `&MISC` |
| `skin_temp` | K | Land surface skin temperature → `TMP_FRONT` in `&SURF` for the ground surface |
| `surface_pres` | Pa | Surface pressure → `P_INF` in `&MISC` |

---

## FDS RAMP file structure

The generated `.txt` file contains a `&WIND` namelist followed by three sets
of `&RAMP` namelists:

```
! ERA5 FDS Wind & Temperature Profile
! Date : 2024-06-01  12:00 UTC
! Lat  : 49.5832  Lon : 18.4408
! T_2m : 293.15 K  |  Skin T : 298.40 K  |  Pres : 97800.00 Pa
!
&WIND SPEED=4.32, RAMP_SPEED_Z='spd', RAMP_DIRECTION_Z='dir', RAMP_TMP0_Z='tmp_profile', DIRECTION=247.3/
!
! ERA5 Wind Speed Profile
&RAMP ID='spd', Z=257.00, F=4.32/
&RAMP ID='spd', Z=312.45, F=6.10/
...
!
! ERA5 Wind Direction Profile
&RAMP ID='dir', Z=257.00, F=247.3/
&RAMP ID='dir', Z=312.45, F=251.8/
...
!
! ERA5 Temperature Ratios  (T(z) / T_2m)
&RAMP ID='tmp_profile', Z=285.10, F=0.997/
&RAMP ID='tmp_profile', Z=450.30, F=0.983/
...
```

### `spd` — wind speed profile

Derived from ERA5 pressure-level U and V wind components converted to speed
via `sqrt(u² + v²)`. The ERA5 10 m wind (`u10`, `v10`) from the single-level
dataset is inserted as an additional point at `z_min + 10` m. The combined
array is sorted by altitude before writing, so the 10 m point sits correctly
in the profile even when `z_min` is above sea level.

### `dir` — wind direction profile

Meteorological convention: the direction the wind is coming **from**, in
degrees clockwise from North. Computed as `arctan2(u, v) % 360`. The same
10 m anchor point and altitude sorting applied to speed is applied here.

### `tmp_profile` — temperature ratio profile

`T(z) / T_2m` at each pressure level, sorted bottom to top. The 2 m
temperature is used as the normalisation reference, consistent with FDS
`TMPA`. No surface anchor point is added — the profile uses pressure-level
data only, exactly as ERA5 provides it.

---

## ERA5 pressure levels

All 37 standard ERA5 pressure levels are requested (1 hPa to 1000 hPa).
Geopotential `z` (m² s⁻²) is converted to geometric altitude above MSL using:

```
z_geometric = (Re × z_geopotential/g₀) / (Re − z_geopotential/g₀)
```

where `Re = 6 356 766 m` and `g₀ = 9.80665 m s⁻²`.

---

## Notes

- ERA5 data has a native resolution of 0.25° (~28 km). The download is clipped
  to a 0.25° box around the target point and the nearest grid cell is selected,
  so the profile represents the ERA5 column at that location.
- ERA5 reanalysis data is available from 1940 to present with a delay of
  approximately 5 days.
- The CDS API queues requests — download time depends on server load and can
  range from seconds to several minutes.
- Downloaded NetCDF files are kept after the run and can be inspected with
  xarray or any NetCDF viewer. Re-running the script will overwrite them.
- When used via `build_fds.py`, `z_min`, `lat`, `lon`, `date`, and `hour` are
  all passed automatically from the shared parameter block — no duplication
  is needed.
