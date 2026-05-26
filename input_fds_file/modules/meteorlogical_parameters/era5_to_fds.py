"""
era5_to_fds.py
--------------
Downloads ERA5 single-level and pressure-level data for a given location
and time, then writes meteorological profiles (wind speed/direction and
temperature) in the FDS RAMP format.

Requirements:
    pip install cdsapi netCDF4 numpy scipy

CDS API key:
    Create ~/.cdsapirc with:
        url: https://cds.climate.copernicus.eu/api/v2
        key: <your-uid>:<your-api-key>

Output:
    met_wind.txt   -- FDS &WIND and &RAMP blocks for speed and direction
    met_temp.txt   -- FDS &RAMP blocks for temperature ratio profiles
"""

import cdsapi
import netCDF4 as nc
import numpy as np
import os
import argparse
from datetime import datetime


# ---------------------------------------------------------------------------
# Configuration — override via params.txt or command-line arguments
# ---------------------------------------------------------------------------

DEFAULTS = {
    # Target location
    "lat": 48.75,
    "lon": 2.75,

    # Date and hour (UTC) of the simulation start
    "date": "2024-06-01",
    "hour": 12,

    # Height above sea level of the domain bottom (zmin), in metres
    # Used to offset the 10 m and 2 m ERA5 surface levels
    "zmin": 86.0,

    # Reference temperature for FDS temperature ramp normalisation (Kelvin)
    # FDS expects F = T / temperature_fix
    "temperature_fix": 293.15,

    # Pressure levels to download (hPa) — choose levels that span your domain
    "pressure_levels": [1000, 975, 950, 925, 900, 875, 850, 825, 800, 775,
                        750, 700, 650, 600, 550, 500],

    # Output file paths
    "out_wind": "met_wind.txt",
    "out_temp": "met_temp.txt",

    # Temporary NetCDF download paths
    "nc_surface": "era5_surface.nc",
    "nc_pressure": "era5_pressure.nc",
}


# ---------------------------------------------------------------------------
# Argument parsing (all parameters optional; defaults come from DEFAULTS)
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Download ERA5 data and convert to FDS met RAMP format."
    )
    p.add_argument("--lat",              type=float, default=DEFAULTS["lat"])
    p.add_argument("--lon",              type=float, default=DEFAULTS["lon"])
    p.add_argument("--date",             type=str,   default=DEFAULTS["date"],
                   help="YYYY-MM-DD")
    p.add_argument("--hour",             type=int,   default=DEFAULTS["hour"],
                   help="UTC hour (0-23)")
    p.add_argument("--zmin",             type=float, default=DEFAULTS["zmin"],
                   help="Domain bottom height above sea level (m)")
    p.add_argument("--temperature_fix",  type=float, default=DEFAULTS["temperature_fix"],
                   help="Reference temperature for FDS ramp normalisation (K)")
    p.add_argument("--out_wind",         type=str,   default=DEFAULTS["out_wind"])
    p.add_argument("--out_temp",         type=str,   default=DEFAULTS["out_temp"])
    p.add_argument("--nc_surface",       type=str,   default=DEFAULTS["nc_surface"])
    p.add_argument("--nc_pressure",      type=str,   default=DEFAULTS["nc_pressure"])
    p.add_argument("--keep_nc",          action="store_true",
                   help="Keep downloaded NetCDF files after conversion")
    return p.parse_args()


# ---------------------------------------------------------------------------
# ERA5 download
# ---------------------------------------------------------------------------

def download_surface(cfg):
    """Download ERA5 single-level variables for the target location and time."""
    print("Downloading ERA5 surface data...")
    c = cdsapi.Client()

    # Build a small bounding box around the target point (+/- 0.5 deg)
    area = [cfg.lat + 0.5, cfg.lon - 0.5, cfg.lat - 0.5, cfg.lon + 0.5]
    hour_str = f"{cfg.hour:02d}:00"

    c.retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": "reanalysis",
            "variable": [
                "10m_u_component_of_wind",
                "10m_v_component_of_wind",
                "100m_u_component_of_wind",
                "100m_v_component_of_wind",
                "2m_temperature",
                "skin_temperature",
                "surface_pressure",
            ],
            "year":  cfg.date[:4],
            "month": cfg.date[5:7],
            "day":   cfg.date[8:10],
            "time":  hour_str,
            "area":  area,
            "format": "netcdf",
        },
        cfg.nc_surface,
    )
    print(f"  Saved to {cfg.nc_surface}")


def download_pressure(cfg):
    """Download ERA5 pressure-level variables for the target location and time."""
    print("Downloading ERA5 pressure-level data...")
    c = cdsapi.Client()

    area = [cfg.lat + 0.5, cfg.lon - 0.5, cfg.lat - 0.5, cfg.lon + 0.5]
    hour_str = f"{cfg.hour:02d}:00"

    c.retrieve(
        "reanalysis-era5-pressure-levels",
        {
            "product_type": "reanalysis",
            "variable": [
                "u_component_of_wind",
                "v_component_of_wind",
                "temperature",
            ],
            "pressure_level": [str(lv) for lv in DEFAULTS["pressure_levels"]],
            "year":  cfg.date[:4],
            "month": cfg.date[5:7],
            "day":   cfg.date[8:10],
            "time":  hour_str,
            "area":  area,
            "format": "netcdf",
        },
        cfg.nc_pressure,
    )
    print(f"  Saved to {cfg.nc_pressure}")


# ---------------------------------------------------------------------------
# Interpolation helper
# ---------------------------------------------------------------------------

def nearest_latlon(lats, lons, target_lat, target_lon):
    """Return indices of the grid point nearest to (target_lat, target_lon)."""
    dist = (lats - target_lat) ** 2 + (lons - target_lon) ** 2
    idx = np.unravel_index(np.argmin(dist), dist.shape)
    return idx


# ---------------------------------------------------------------------------
# Extract profiles from NetCDF
# ---------------------------------------------------------------------------

def extract_surface(nc_path, cfg):
    """
    Extract surface-level wind and temperature from the downloaded NetCDF.

    Returns dict with keys:
        u10, v10       -- 10 m wind components (m/s)
        u100, v100     -- 100 m wind components (m/s)
        t2m            -- 2 m temperature (K)
        skt            -- skin temperature (K)
        sp             -- surface pressure (Pa)
    """
    ds = nc.Dataset(nc_path)

    lats = ds.variables["latitude"][:]
    lons = ds.variables["longitude"][:]

    # ERA5 NetCDF may have 1-D or 2-D lat/lon — handle both
    if lats.ndim == 1:
        lon_grid, lat_grid = np.meshgrid(lons, lats)
    else:
        lat_grid, lon_grid = lats, lons

    iy, ix = nearest_latlon(lat_grid, lon_grid, cfg.lat, cfg.lon)

    def get(varname):
        v = ds.variables[varname]
        # Shape is typically (time, lat, lon) or (lat, lon)
        arr = v[:]
        if arr.ndim == 3:
            return float(arr[0, iy, ix])
        elif arr.ndim == 2:
            return float(arr[iy, ix])
        else:
            return float(arr[0])

    result = {
        "u10":  get("u10"),
        "v10":  get("v10"),
        "u100": get("u100"),
        "v100": get("v100"),
        "t2m":  get("t2m"),
        "skt":  get("skt"),
        "sp":   get("sp"),
    }
    ds.close()
    return result


def extract_pressure_levels(nc_path, cfg):
    """
    Extract pressure-level wind and temperature profiles.

    Returns:
        levels   -- list of pressure levels (hPa), sorted descending (surface first)
        u_prof   -- u wind at each level (m/s)
        v_prof   -- v wind at each level (m/s)
        t_prof   -- temperature at each level (K)
    """
    ds = nc.Dataset(nc_path)

    lats = ds.variables["latitude"][:]
    lons = ds.variables["longitude"][:]

    if lats.ndim == 1:
        lon_grid, lat_grid = np.meshgrid(lons, lats)
    else:
        lat_grid, lon_grid = lats, lons

    iy, ix = nearest_latlon(lat_grid, lon_grid, cfg.lat, cfg.lon)

    pressure = ds.variables["pressure_level"][:]   # hPa, may be named 'level'
    # Fallback name
    if "pressure_level" not in ds.variables:
        pressure = ds.variables["level"][:]

    def get_profile(varname):
        v = ds.variables[varname][:]
        # Shape: (time, level, lat, lon) or (level, lat, lon)
        if v.ndim == 4:
            return v[0, :, iy, ix]
        elif v.ndim == 3:
            return v[:, iy, ix]
        else:
            return v[:, 0]

    u_prof = np.array(get_profile("u"))
    v_prof = np.array(get_profile("v"))
    t_prof = np.array(get_profile("t"))
    levels = np.array(pressure)

    # Sort from surface (high pressure) to top (low pressure)
    sort_idx = np.argsort(levels)[::-1]
    ds.close()

    return levels[sort_idx], u_prof[sort_idx], v_prof[sort_idx], t_prof[sort_idx]


# ---------------------------------------------------------------------------
# Pressure level → approximate altitude (hypsometric equation)
# ---------------------------------------------------------------------------

def pressure_to_altitude(p_hPa, p_surface_hPa, t_surface_K):
    """
    Estimate geometric altitude above ground for a pressure level using the
    hypsometric equation. Returns height in metres above the surface.

        z = (R * T_avg / g) * ln(p_surface / p)

    where T_avg is approximated as t_surface (good for lower troposphere).
    """
    R = 287.05   # J/(kg·K), dry air gas constant
    g = 9.80665  # m/s²
    z = (R * t_surface_K / g) * np.log(p_surface_hPa / p_hPa)
    return z


# ---------------------------------------------------------------------------
# Wind: speed and direction
# ---------------------------------------------------------------------------

def wind_speed_direction(u, v):
    """
    Convert (u, v) wind components to speed (m/s) and meteorological direction (deg).
    Meteorological convention: direction FROM which wind blows, 0=N, 90=E, 180=S, 270=W.
    """
    speed = np.sqrt(u**2 + v**2)
    # atan2 gives math direction (from east, counterclockwise)
    # Convert to meteorological direction (from north, clockwise, direction FROM)
    direction = (270.0 - np.degrees(np.arctan2(v, u))) % 360.0
    return float(speed), float(direction)


# ---------------------------------------------------------------------------
# Write FDS wind RAMP file
# ---------------------------------------------------------------------------

def write_wind_ramp(cfg, surface, levels_hPa, u_prof, v_prof, t_surf_K, sp_Pa):
    """
    Build the FDS wind and speed/direction RAMP entries.

    Z values:
      - zmin + 10  m  from 10 m surface wind
      - zmin + 100 m  from 100 m surface wind
      - pressure levels converted to height above sea level (no zmin offset)
    """
    z_entries = []   # list of (z_abs, speed, direction)

    # --- Surface levels ---
    z_10  = cfg.zmin + 10.0
    z_100 = cfg.zmin + 100.0

    spd_10,  dir_10  = wind_speed_direction(surface["u10"],  surface["v10"])
    spd_100, dir_100 = wind_speed_direction(surface["u100"], surface["v100"])

    z_entries.append((z_10,  spd_10,  dir_10))
    z_entries.append((z_100, spd_100, dir_100))

    # --- Pressure levels ---
    p_surf_hPa = sp_Pa / 100.0
    for i, p in enumerate(levels_hPa):
        z_agl = pressure_to_altitude(p, p_surf_hPa, t_surf_K)
        z_abs = cfg.zmin + z_agl       # height above sea level
        if z_abs <= z_100:             # skip levels below 100 m (already covered)
            continue
        spd, dirn = wind_speed_direction(u_prof[i], v_prof[i])
        z_entries.append((z_abs, spd, dirn))

    # Sort by height
    z_entries.sort(key=lambda x: x[0])

    lines = []
    lines.append("! Wind profile generated from ERA5 data")
    lines.append(f"! Location: lat={cfg.lat}, lon={cfg.lon}")
    lines.append(f"! Date/time: {cfg.date} {cfg.hour:02d}:00 UTC")
    lines.append("!")
    lines.append("&WIND SPEED=1., RAMP_SPEED_Z='spd', RAMP_DIRECTION_Z='dir'/")
    lines.append("")

    for z, spd, _ in z_entries:
        lines.append(f"&RAMP ID='spd', Z={z:.2f}, F={spd:.4f}/")

    lines.append("")

    for z, _, dirn in z_entries:
        lines.append(f"&RAMP ID='dir', Z={z:.2f}, F={dirn:.2f}/")

    with open(cfg.out_wind, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Wind RAMP written to {cfg.out_wind}")
    return z_entries


# ---------------------------------------------------------------------------
# Write FDS temperature RAMP file
# ---------------------------------------------------------------------------

def write_temp_ramp(cfg, surface, levels_hPa, t_prof, sp_Pa):
    """
    Build the FDS temperature RAMP entries.

    F = T / temperature_fix  (ratio, dimensionless)

    Z values:
      - zmin + 2 m  from 2 m surface temperature
      - pressure levels converted to height above sea level
    """
    t_surf_K = surface["t2m"]
    p_surf_hPa = sp_Pa / 100.0

    z_entries = []   # list of (z_abs, T_K)

    # --- Surface level: 2 m ---
    z_2m = cfg.zmin + 2.0
    z_entries.append((z_2m, t_surf_K))

    # --- Pressure levels ---
    for i, p in enumerate(levels_hPa):
        z_agl = pressure_to_altitude(p, p_surf_hPa, t_surf_K)
        z_abs = cfg.zmin + z_agl
        if z_abs <= z_2m:
            continue
        z_entries.append((z_abs, float(t_prof[i])))

    z_entries.sort(key=lambda x: x[0])

    lines = []
    lines.append("! Temperature profile generated from ERA5 data")
    lines.append(f"! Location: lat={cfg.lat}, lon={cfg.lon}")
    lines.append(f"! Date/time: {cfg.date} {cfg.hour:02d}:00 UTC")
    lines.append(f"! temperature_fix = {cfg.temperature_fix} K")
    lines.append("!")

    for z, T in z_entries:
        ratio = T / cfg.temperature_fix
        lines.append(f"&RAMP ID='temp', Z={z:.2f}, F={ratio:.6f}/")

    with open(cfg.out_temp, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Temperature RAMP written to {cfg.out_temp}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    cfg = parse_args()

    # --- Download ---
    download_surface(cfg)
    download_pressure(cfg)

    # --- Extract ---
    print("Extracting surface variables...")
    surface = extract_surface(cfg.nc_surface, cfg)

    print("Extracting pressure-level profiles...")
    levels_hPa, u_prof, v_prof, t_prof = extract_pressure_levels(
        cfg.nc_pressure, cfg
    )

    # --- Convert and write ---
    print("Writing FDS met RAMPs...")
    write_wind_ramp(
        cfg, surface, levels_hPa, u_prof, v_prof,
        t_surf_K=surface["t2m"], sp_Pa=surface["sp"]
    )
    write_temp_ramp(cfg, surface, levels_hPa, t_prof, sp_Pa=surface["sp"])

    # --- Cleanup ---
    if not cfg.keep_nc:
        for f in [cfg.nc_surface, cfg.nc_pressure]:
            if os.path.exists(f):
                os.remove(f)
        print("Temporary NetCDF files removed.")

    print("\nDone. Output files:")
    print(f"  {cfg.out_wind}")
    print(f"  {cfg.out_temp}")


if __name__ == "__main__":
    main()
