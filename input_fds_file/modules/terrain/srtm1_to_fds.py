"""
srtm_to_fds.py
==============
Module to download SRTM1 elevation data and convert it to FDS &OBST terrain cards.

Designed to be used as a standalone module called from external code.
The public API is:

    get_terrain(lat, lon, size_m, output_file, resolution_m=30, ...)

or the lower-level helpers:

    download_srtm_grid(lat, lon, size_m, resolution_m)  -> (x, y, z, zmin)
    write_terrain(x, y, z, zmin, terrain_limit_l, terrain_limit_u, file_handle)

Dependencies
------------
    pip install elevation numpy scipy pyproj
    (elevation wraps the SRTM GDAL downloader and requires gdal / rio on PATH)
"""

from __future__ import annotations

import os
import math
import tempfile
import subprocess
from typing import Optional

import numpy as np
from scipy.interpolate import RegularGridInterpolator
from pyproj import Transformer


# ---------------------------------------------------------------------------
# Low-level helpers (identical interface to the original code)
# ---------------------------------------------------------------------------

def write_terrain(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    zmin: float,
    terrain_limit_l: Optional[float],
    terrain_limit_u: Optional[float],
    file_handle,
) -> None:
    """
    Write terrain data as FDS &OBST cards to *file_handle*.

    Parameters
    ----------
    x, y        : 1-D coordinate arrays (metres, centred on the source point).
    z           : 2-D elevation array, shape (len(y), len(x)).
    zmin        : Floor elevation written as the lower z bound of every obstruction.
    terrain_limit_l : Inner half-width of the hollow square (None = no inner hole).
    terrain_limit_u : Outer half-width of the hollow square (None = no outer cap).
    file_handle : Open file object to write into.
    """
    resolution_local = x[1] - x[0]
    print(f"\nTerrain {resolution_local:.2f} m", file=file_handle)

    for i in range(len(x) - 1):
        for j in range(len(y) - 1):
            x_val = x[i]
            y_val = y[j]

            is_within_outer = terrain_limit_u is None or (
                abs(x_val) < terrain_limit_u and abs(y_val) < terrain_limit_u
            )
            is_outside_inner = terrain_limit_l is None or (
                abs(x_val) >= terrain_limit_l or abs(y_val) >= terrain_limit_l
            )

            if is_within_outer and is_outside_inner:
                print(
                    f"&OBST XB={x[i]:.2f},{x[i+1]:.2f},"
                    f"{y[j]:.2f},{y[j+1]:.2f},"
                    f"{zmin:.2f},{z[j, i]:.2f}/",
                    file=file_handle,
                )


# ---------------------------------------------------------------------------
# SRTM download + resampling
# ---------------------------------------------------------------------------

def _bounds_from_centre(lat: float, lon: float, size_m: float):
    """
    Return (south, north, west, east) in geographic degrees for a square domain
    of *size_m* metres centred on (*lat*, *lon*).
    """
    # 1 degree latitude ~ 111 320 m (constant); longitude varies with cos(lat)
    half = size_m / 2.0
    delta_lat = half / 111_320.0
    delta_lon = half / (111_320.0 * math.cos(math.radians(lat)))
    return (
        lat - delta_lat,
        lat + delta_lat,
        lon - delta_lon,
        lon + delta_lon,
    )


def download_srtm_grid(
    lat: float,
    lon: float,
    size_m: float,
    resolution_m: float = 30,
    cache_dir: Optional[str] = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """
    Download SRTM1 data for a square domain and resample to *resolution_m*.

    Parameters
    ----------
    lat, lon      : Centre of the domain (decimal degrees, WGS-84).
    size_m        : Side length of the square domain in metres.
    resolution_m  : Target grid spacing in metres (default 30).
    cache_dir     : Directory for the elevation package cache.
                    Defaults to ``~/.cache/elevation``.

    Returns
    -------
    x, y   : 1-D arrays of local coordinates (metres), centred on the source.
    z      : 2-D elevation array, shape (len(y), len(x)).
    zmin   : Second-lowest unique elevation (floor for FDS obstructions).
    """
    try:
        import elevation  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "The 'elevation' package is required. Install it with:\n"
            "    pip install elevation\n"
            "and make sure GDAL command-line tools are available."
        ) from exc

    try:
        from osgeo import gdal  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "GDAL Python bindings are required. Install with:\n"
            "    pip install gdal   (or conda install -c conda-forge gdal)"
        ) from exc

    south, north, west, east = _bounds_from_centre(lat, lon, size_m)

    # --- Download SRTM1 tile(s) clipped to bounding box --------------------
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_tif = os.path.join(tmpdir, "srtm_raw.tif")

        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

        elevation.clip(
            bounds=(west, south, east, north),
            output=raw_tif,
            product="SRTM1",
            cache_dir=cache_dir,
        )

        # --- Read the raw GeoTIFF ------------------------------------------
        ds = gdal.Open(raw_tif)
        if ds is None:
            raise RuntimeError(f"GDAL could not open the downloaded file: {raw_tif}")

        gt = ds.GetGeoTransform()   # (west, res_x, 0, north, 0, -res_y)
        band = ds.GetRasterBand(1)
        z_raw = band.ReadAsArray().astype(float)
        nodata = band.GetNoDataValue()
        if nodata is not None:
            z_raw[z_raw == nodata] = np.nan

        nx_raw = ds.RasterXSize
        ny_raw = ds.RasterYSize
        lon_raw = gt[0] + gt[1] * (np.arange(nx_raw) + 0.5)
        lat_raw = gt[3] + gt[5] * (np.arange(ny_raw) + 0.5)
        ds = None  # close

    # --- Project to UTM (metric) centred on the source point ---------------
    utm_zone = int((lon + 180) / 6) + 1
    hemisphere = "north" if lat >= 0 else "south"
    epsg_utm = 32600 + utm_zone if lat >= 0 else 32700 + utm_zone

    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg_utm}", always_xy=True)
    src_x, src_y = transformer.transform(lon, lat)

    lon_grid, lat_grid = np.meshgrid(lon_raw, lat_raw)
    x_utm, y_utm = transformer.transform(lon_grid, lat_grid)

    # Shift to source-centred coordinates
    x_utm -= src_x
    y_utm -= src_y

    # --- Resample onto a regular metric grid --------------------------------
    half = size_m / 2.0
    n_cells = int(round(size_m / resolution_m))
    x_new = np.linspace(-half, half, n_cells + 1)
    y_new = np.linspace(-half, half, n_cells + 1)

    # Build interpolator on the (irregular after projection) raw grid.
    # We use a simple nearest-neighbour via RegularGridInterpolator on the
    # original row/col axes, which is accurate enough for terrain.
    row_coords = y_utm[:, 0]   # y varies along rows
    col_coords = x_utm[0, :]   # x varies along columns

    # Ensure monotonically increasing for the interpolator
    if row_coords[0] > row_coords[-1]:
        row_coords = row_coords[::-1]
        z_raw = z_raw[::-1, :]
    if col_coords[0] > col_coords[-1]:
        col_coords = col_coords[::-1]
        z_raw = z_raw[:, ::-1]

    interp = RegularGridInterpolator(
        (row_coords, col_coords),
        z_raw,
        method="linear",
        bounds_error=False,
        fill_value=np.nan,
    )

    xx, yy = np.meshgrid(x_new, y_new)
    z_resampled = interp((yy, xx))

    # Fill any NaN gaps with nearest valid value (simple approach)
    nan_mask = np.isnan(z_resampled)
    if nan_mask.any():
        from scipy.ndimage import distance_transform_edt  # noqa: PLC0415
        _, idx = distance_transform_edt(nan_mask, return_indices=True)
        z_resampled[nan_mask] = z_resampled[idx[0][nan_mask], idx[1][nan_mask]]

    z_resampled = np.round(z_resampled, 2)
    x_new = np.round(x_new, 2)
    y_new = np.round(y_new, 2)

    # zmin = second-lowest elevation (mirrors original logic)
    flat = z_resampled.ravel()
    zmin = np.sort(np.unique(flat))[1] if np.unique(flat).size > 1 else flat[0]
    z_resampled[z_resampled < zmin] = zmin

    return x_new, y_new, z_resampled, float(zmin)


# ---------------------------------------------------------------------------
# Multi-resolution convenience wrapper (mirrors the original __main__ block)
# ---------------------------------------------------------------------------

def get_terrain(
    lat: float,
    lon: float,
    size_m: float,
    output_file: str,
    resolutions: Optional[list[dict]] = None,
    cache_dir: Optional[str] = None,
) -> None:
    """
    Download SRTM1 data and write a multi-resolution FDS terrain file.

    This is the main entry point intended to be called from external code.

    Parameters
    ----------
    lat, lon      : Centre of the domain (decimal degrees, WGS-84).
    size_m        : Outer side length of the full domain in metres.
    output_file   : Path of the FDS text file to write (created / overwritten).
    resolutions   : List of dicts with keys:
                        'resolution'  – grid spacing in metres
                        'lower_limit' – inner half-width for the hollow square
                                        (None = no inner exclusion zone)
                        'upper_limit' – outer half-width for the hollow square
                                        (None = no outer clipping)
                    If omitted, a sensible four-level default is used that
                    mirrors the original script's test_cases.
    cache_dir     : Directory for the elevation package's tile cache.

    Example
    -------
    >>> from srtm_to_fds import get_terrain
    >>> get_terrain(
    ...     lat=45.832,
    ...     lon=6.865,
    ...     size_m=900,
    ...     output_file="terrain.fds",
    ... )
    """
    if resolutions is None:
        # Default nested-resolution scheme (coarse to fine, hollow squares)
        half = size_m / 2.0
        resolutions = [
            {"resolution": 30, "lower_limit": half * 0.90, "upper_limit": None},
            {"resolution": 10, "lower_limit": half * 0.30, "upper_limit": half * 0.95},
            {"resolution": 5,  "lower_limit": half * 0.10, "upper_limit": half * 0.33},
            {"resolution": 2,  "lower_limit": None,        "upper_limit": half * 0.11},
        ]

    combined_zmin = math.inf

    # Pre-download all resolutions so combined_zmin is known before writing
    grids: list[dict] = []
    for case in resolutions:
        res = case["resolution"]
        print(f"  Downloading {res} m resolution data …")
        x, y, z, zmin = download_srtm_grid(lat, lon, size_m, res, cache_dir)
        combined_zmin = min(combined_zmin, zmin)
        grids.append({"x": x, "y": y, "z": z, "case": case})

    # Write FDS file
    with open(output_file, "w") as fh:
        print(f"! Terrain generated by srtm_to_fds.py", file=fh)
        print(f"! Centre: lat={lat}, lon={lon}  |  Domain: {size_m} m", file=fh)
        print(f"! zmin (floor) = {combined_zmin:.2f} m\n", file=fh)

        for item in grids:
            write_terrain(
                item["x"],
                item["y"],
                item["z"],
                combined_zmin,
                item["case"]["lower_limit"],
                item["case"]["upper_limit"],
                fh,
            )

    print(f"Terrain written to '{output_file}'.")


# ---------------------------------------------------------------------------
# Optional CLI convenience
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Download SRTM1 terrain and write an FDS &OBST file."
    )
    parser.add_argument("lat",  type=float, help="Latitude  of domain centre (°)")
    parser.add_argument("lon",  type=float, help="Longitude of domain centre (°)")
    parser.add_argument("size", type=float, help="Domain side length (m)")
    parser.add_argument("-o", "--output", default="terrain.fds", help="Output FDS file")
    parser.add_argument("--cache-dir", default=None, help="Elevation cache directory")
    args = parser.parse_args()

    get_terrain(args.lat, args.lon, args.size, args.output, cache_dir=args.cache_dir)
