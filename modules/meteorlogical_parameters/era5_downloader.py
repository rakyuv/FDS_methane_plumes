"""
era5_downloader.py
==================
Downloads ERA5 single-level and pressure-level variables for a given
timestamp and location.

    Single-level variables  → NetCDF  (.nc)
    Pressure-level variables → FDS-style RAMP text file (.txt)

Usage — standalone (edit the USER PARAMETERS block below, then run):
    python era5_downloader.py

Usage — as a module imported by another script:
    from era5_downloader import run

    result = run(
        lat      = 48.8566,
        lon      =  2.3522,
        date     = "2023-07-15",   # YYYY-MM-DD
        hour     = 12,             # UTC hour, integer 0-23
        out_dir  = "./outputs",    # optional, default "."
    )
    # result is a dict:
    # {
    #   "netcdf_single" : "/path/to/era5_single_levels.nc",
    #   "netcdf_pressure": "/path/to/era5_pressure_levels.nc",
    #   "ramp_txt"      : "/path/to/era5_fds_ramp_2023-07-15_12UTC.txt",
    # }

Requirements:
    pip install cdsapi xarray netCDF4 numpy
    A valid ~/.cdsapirc file with your CDS API key.
"""

import cdsapi
import xarray as xr
import numpy as np
import os
from datetime import datetime

# ===========================================================================
# USER PARAMETERS  ← edit this block when running as a standalone script
# ===========================================================================

LAT     =  48.8566   # decimal degrees  (positive = North)
LON     =   2.3522   # decimal degrees  (positive = East)
DATE    = "2023-07-15"  # YYYY-MM-DD
HOUR    =  12           # UTC hour, integer 0–23
OUT_DIR = "."           # output folder (created if it doesn't exist)

# ===========================================================================


# ---------------------------------------------------------------------------
# ERA5 variable lists
# ---------------------------------------------------------------------------

SINGLE_LEVEL_VARIABLES = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "surface_pressure",
    "skin_temperature",
]

PRESSURE_LEVEL_VARIABLES = [
    "u_component_of_wind",
    "v_component_of_wind",
    "temperature",
    "geopotential",
]

# All 37 standard ERA5 pressure levels (hPa)
PRESSURE_LEVELS = [
    "1", "2", "3", "5", "7",
    "10", "20", "30", "50", "70",
    "100", "125", "150", "175",
    "200", "225", "250",
    "300", "350",
    "400", "450",
    "500", "550",
    "600", "650",
    "700", "750", "775",
    "800", "825", "850",
    "875", "900", "925",
    "950", "975", "1000",
]


# ---------------------------------------------------------------------------
# Physics helpers
# ---------------------------------------------------------------------------

def _geopotential_to_altitude(phi):
    """Convert geopotential (m² s⁻²) to geometric altitude (m) above MSL."""
    g0 = 9.80665    # standard gravity [m s⁻²]
    Re = 6_356_766  # Earth radius     [m]
    z_gp  = phi / g0
    return (Re * z_gp) / (Re - z_gp)


def _wind_speed(u, v):
    return np.sqrt(u ** 2 + v ** 2)

def _wind_direction(u, v):
    """Meteorological wind direction in degrees (direction wind is coming FROM)."""
    return np.degrees(np.arctan2(u, v)) % 360

# ---------------------------------------------------------------------------
# Internal download helpers
# ---------------------------------------------------------------------------

def _build_params(lat, lon, date, hour):
    """Validate inputs and return a normalised params dict."""
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    if not (-90 <= lat <= 90):
        raise ValueError(f"lat={lat} out of range [-90, 90]")
    if not (-180 <= lon <= 180):
        raise ValueError(f"lon={lon} out of range [-180, 180]")
    if not (0 <= hour <= 23):
        raise ValueError(f"hour={hour} must be 0–23")
    return {
        "year" : date_obj.strftime("%Y"),
        "month": date_obj.strftime("%m"),
        "day"  : date_obj.strftime("%d"),
        "time" : f"{hour:02d}:00",
        "lat"  : lat,
        "lon"  : lon,
        "date_str": date,
        "hour" : hour,
    }


def _area(lat, lon, margin=0.25):
    """CDS area box [N, W, S, E] around a point."""
    return [lat + margin, lon - margin, lat - margin, lon + margin]


def _download_single_levels(c, p, out_dir):
    path = os.path.join(out_dir, "era5_single_levels.nc")
    print("[1/3] Downloading single-level variables …")
    c.retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": "reanalysis",
            "variable"    : SINGLE_LEVEL_VARIABLES,
            "year" : p["year"],
            "month": p["month"],
            "day"  : p["day"],
            "time" : p["time"],
            "area" : _area(p["lat"], p["lon"]),
            "format": "netcdf",
        },
        path,
    )
    print(f"  ✓ {path}")
    return path


def _download_pressure_levels(c, p, out_dir):
    path = os.path.join(out_dir, "era5_pressure_levels.nc")
    print("[2/3] Downloading pressure-level variables …")
    c.retrieve(
        "reanalysis-era5-pressure-levels",
        {
            "product_type" : "reanalysis",
            "variable"     : PRESSURE_LEVEL_VARIABLES,
            "pressure_level": PRESSURE_LEVELS,
            "year" : p["year"],
            "month": p["month"],
            "day"  : p["day"],
            "time" : p["time"],
            "area" : _area(p["lat"], p["lon"]),
            "format": "netcdf",
        },
        path,
    )
    print(f"  ✓ {path}")
    return path

def _write_fds_ramp(pl_nc, sl_nc, p, out_dir, z_min):
    print("[3/3] Generating FDS RAMP profile …")

    ds_pl = xr.open_dataset(pl_nc)
    ds_sl = xr.open_dataset(sl_nc)

    rename_dict = {}
    for old_dim, new_dim in [('valid_time', 'time'), ('lat', 'latitude'), ('lon', 'longitude')]:
        if old_dim in ds_pl.dims:
            rename_dict[old_dim] = new_dim
    if rename_dict:
        ds_pl = ds_pl.rename(rename_dict)
        ds_sl = ds_sl.rename(rename_dict)

    ds_pl = ds_pl.sel(latitude=p["lat"], longitude=p["lon"], method="nearest").isel(time=0)
    ds_sl = ds_sl.sel(latitude=p["lat"], longitude=p["lon"], method="nearest").isel(time=0)

    # Scalar surface quantities
    t2m       = float(ds_sl["t2m"].values)
    skin_temp = float(ds_sl["skt"].values)
    surf_pres = float(ds_sl["sp"].values)

    print(f"  T_2m        = {t2m:.2f} K  ({t2m - 273.15:.2f} °C)")
    print(f"  Skin temp   = {skin_temp:.2f} K  ({skin_temp - 273.15:.2f} °C)")
    print(f"  Surface pres= {surf_pres:.2f} Pa")

    # Pressure-level arrays
    phi   = ds_pl["z"].values.flatten()
    u_arr = ds_pl["u"].values.flatten()
    v_arr = ds_pl["v"].values.flatten()
    t_arr = ds_pl["t"].values.flatten()

    altitudes  = _geopotential_to_altitude(phi)
    speeds     = _wind_speed(u_arr, v_arr)
    directions = _wind_direction(u_arr, v_arr)
    t_ratio    = t_arr / t2m

    # Sort bottom → top
    idx        = np.argsort(altitudes)
    altitudes  = altitudes[idx]
    speeds     = speeds[idx]
    directions = directions[idx]
    t_ratio    = t_ratio[idx]

    # 10 m wind anchored at z_min + 10
    u10     = float(ds_sl["u10"].values)
    v10     = float(ds_sl["v10"].values)
    spd_10m = float(_wind_speed(u10, v10))
    dir_10m = float(_wind_direction(u10, v10))
    z_10m   = z_min + 10.0

    # Speed and direction: insert 10 m point then re-sort
    altitudes_sd = np.concatenate([[z_10m],   altitudes])
    speeds       = np.concatenate([[spd_10m], speeds])
    directions   = np.concatenate([[dir_10m], directions])

    idx          = np.argsort(altitudes_sd)
    altitudes_sd = altitudes_sd[idx]
    speeds       = speeds[idx]
    directions   = directions[idx]

    # Temperature: pressure levels only, already sorted, no 10 m anchor needed

    ramp_path = os.path.join(out_dir, f"era5_fds_ramp_{p['date_str']}_{p['hour']:02d}UTC.txt")

    with open(ramp_path, "w") as f:
        f.write(
            f"! ERA5 FDS Wind & Temperature Profile\n"
            f"! Date : {p['date_str']}  {p['hour']:02d}:00 UTC\n"
            f"! Lat  : {p['lat']:.4f}  Lon : {p['lon']:.4f}\n"
            f"! T_2m : {t2m:.2f} K  |  Skin T : {skin_temp:.2f} K  |  Pres : {surf_pres:.2f} Pa\n!\n"
        )
        f.write(
            f"&WIND SPEED=1, "
            f"RAMP_SPEED_Z='spd', "
            f"RAMP_DIRECTION_Z='dir', "
            f"RAMP_TMP0_Z='tmp_profile', "
            f"!\n! ERA5 Wind Speed Profile\n"
        )
        for z, spd in zip(altitudes_sd, speeds):
            f.write(f"&RAMP ID='spd', Z={z:.2f}, F={spd:.2f}/\n")

        f.write("!\n! ERA5 Wind Direction Profile\n")
        for z, d in zip(altitudes_sd, directions):
            f.write(f"&RAMP ID='dir', Z={z:.2f}, F={d:.2f}/\n")

        f.write("!\n! ERA5 Temperature Ratios  (T(z) / T_2m)\n")
        for z, tr in zip(altitudes, t_ratio):
            f.write(f"&RAMP ID='tmp_profile', Z={z:.2f}, F={tr:.2f}/\n")

    print(f"  ✓ {ramp_path}")
    ds_pl.close()
    ds_sl.close()

    return {
        "ramp_txt"    : ramp_path,
        "t2m"         : t2m,
        "skin_temp"   : skin_temp,
        "surface_pres": surf_pres,
    }

# ---------------------------------------------------------------------------
# Public API  (use this when importing as a module)
# ---------------------------------------------------------------------------

def run(lat, lon, date, hour, z_min=0.0):
    """
    Download ERA5 data and produce output files.

    Parameters
    ----------
    lat     : float  — latitude  in decimal degrees
    lon     : float  — longitude in decimal degrees
    date    : str    — "YYYY-MM-DD"
    hour    : int    — UTC hour (0–23)

    Returns
    -------
    dict with keys:
        "netcdf_single"   – path to single-level NetCDF
        "netcdf_pressure" – path to pressure-level NetCDF
        "ramp_txt"        – path to FDS RAMP text file
    """
    p = _build_params(lat, lon, date, hour)
    c = cdsapi.Client()

    sl_nc   = _download_single_levels(c, p, ".")
    pl_nc   = _download_pressure_levels(c, p, ".")
    result  = _write_fds_ramp(pl_nc, sl_nc, p, ".", z_min=z_min)

    print("\nDone.")
    print(f"  Single-level NetCDF  : {sl_nc}")
    print(f"  Pressure-level NetCDF: {pl_nc}")
    print(f"  FDS RAMP text        : {result['ramp_txt']}\n")

    return result


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run(
        lat     = LAT,
        lon     = LON,
        date    = DATE,
        hour    = HOUR,
    )
