from __future__ import annotations

import os
import math
import tempfile
import re
from typing import Optional

import numpy as np
from scipy.interpolate import RegularGridInterpolator
from pyproj import Transformer

# ---------------------------------------------------------------------------
# FDS Mesh File Parser
# ---------------------------------------------------------------------------

def parse_mesh_file(filepath: str) -> tuple[float, list[dict]]:
    """
    Parses an FDS mesh file to calculate total domain size and resolution tiers.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Could not find the mesh file: {filepath}")

    ijk_re = re.compile(r"IJK\s*=\s*([\d\s,]+)")
    xb_re = re.compile(r"XB\s*=\s*([-\d\s.,]+)")

    raw_meshes = []
    global_max_coord = 0.0

    with open(filepath, "r") as f:
        for line in f:
            if "&MESH" not in line or "XB" not in line:
                continue
            
            ijk_match = ijk_re.search(line)
            xb_match = xb_re.search(line)
            
            if ijk_match and xb_match:
                ijk_tokens = [x.strip() for x in ijk_match.group(1).split(",")]
                ijk = [int(x) for x in ijk_tokens if x]
                
                xb_tokens = [x.strip() for x in xb_match.group(1).split(",")]
                xb = [float(x) for x in xb_tokens if x]
                
                if len(ijk) < 3 or len(xb) < 6:
                    continue

                res_x = round((xb[1] - xb[0]) / ijk[0], 2)
                
                x_half_span = max(abs(xb[0]), abs(xb[1]))
                y_half_span = max(abs(xb[2]), abs(xb[3]))
                local_max = max(x_half_span, y_half_span)
                
                if local_max > global_max_coord:
                    global_max_coord = local_max
                
                raw_meshes.append({
                    "res": res_x,
                    "x1": xb[0], "x2": xb[1],
                    "y1": xb[2], "y2": xb[3]
                })

    if not raw_meshes:
        raise ValueError(f"No valid &MESH cards found in {filepath}")

    size_m = global_max_coord * 2.0
    unique_resolutions = sorted(list(set(m["res"] for m in raw_meshes)))
    resolutions_config = []

    for res in unique_resolutions:
        res_meshes = [m for m in raw_meshes if m["res"] == res]
        min_extent = math.inf
        max_extent = 0.0
        
        for m in res_meshes:
            for x in (m["x1"], m["x2"]):
                for y in (m["y1"], m["y2"]):
                    dist = max(abs(x), abs(y))
                    if dist > max_extent:
                        max_extent = dist
                    if dist < min_extent and dist > 0:
                        min_extent = dist

        lower_limit = None if min_extent < (res * 1.5) else min_extent
        upper_limit = None if math.isclose(max_extent, global_max_coord, abs_tol=res) else max_extent

        resolutions_config.append({
            "resolution": res,
            "lower_limit": lower_limit,
            "upper_limit": upper_limit
        })

    resolutions_config.sort(key=lambda x: x["resolution"], reverse=True)
    return size_m, resolutions_config


def write_terrain(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    zmin: float,
    terrain_limit_l: Optional[float],
    terrain_limit_u: Optional[float],
    file_handle,
) -> None:
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


def _bounds_from_centre(lat: float, lon: float, size_m: float):
    half = size_m / 2.0
    delta_lat = half / 111_320.0
    delta_lon = half / (111_320.0 * math.cos(math.radians(lat)))
    return (
        lat - delta_lat,
        lat + delta_lat,
        lon - delta_lon,
        lon + delta_lon,
    )


# ---------------------------------------------------------------------------
# Core Elevation Loader (Handles Local GeoTIFF or SRTM Fallback)
# ---------------------------------------------------------------------------

def load_terrain_grid(
    lat: float,
    lon: float,
    size_m: float,
    resolution_m: float,
    local_tif: Optional[str] = None,
    cache_dir: Optional[str] = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """
    Loads elevation data resampled to resolution_m. Uses local_tif if 
    resolution_m <= 25 and local_tif is provided; otherwise, falls back to SRTM1.
    """
    from osgeo import gdal

    south, north, west, east = _bounds_from_centre(lat, lon, size_m)

    # Determine UTM projection coordinates for target grid centering
    utm_zone = int((lon + 180) / 6) + 1
    epsg_utm = 32600 + utm_zone if lat >= 0 else 32700 + utm_zone
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg_utm}", always_xy=True)
    src_x, src_y = transformer.transform(lon, lat)

    with tempfile.TemporaryDirectory() as tmpdir:
        working_tif = os.path.join(tmpdir, "working_input.tif")

        # BRANCH 1: Use high-res local file if criteria are met
        if local_tif and resolution_m <= 30:
            if not os.path.exists(local_tif):
                raise FileNotFoundError(f"Local TIFF file not found: {local_tif}")
            print(f"    [Source] Using high-resolution local file: {local_tif}")
            # Map directly to local file path
            working_tif = local_tif
            is_local = True
        
        # BRANCH 2: Fallback to SRTM download
        else:
            print(f"    [Source] Fetching SRTM1 data...")
            try:
                import elevation
            except ImportError as exc:
                raise ImportError("The 'elevation' package is required for SRTM data. Run: pip install elevation") from exc
            
            if cache_dir:
                os.makedirs(cache_dir, exist_ok=True)

            clip_kwargs = {
                "bounds": (west, south, east, north),
                "output": working_tif,
                "product": "SRTM1",
            }
            if cache_dir is not None:
                clip_kwargs["cache_dir"] = cache_dir

            elevation.clip(**clip_kwargs)
            is_local = False

        # --- Process Raster data -------------------------------------------
        ds = gdal.Open(working_tif)
        if ds is None:
            raise RuntimeError(f"GDAL could not open raster file: {working_tif}")

        gt = ds.GetGeoTransform()
        band = ds.GetRasterBand(1)
        z_raw = band.ReadAsArray().astype(float)
        nodata = band.GetNoDataValue()
        if nodata is not None:
            z_raw[z_raw == nodata] = np.nan

        nx_raw = ds.RasterXSize
        ny_raw = ds.RasterYSize

        # Handle local TIFF CRS projection dynamically vs assumed EPSG:4326 for SRTM
        if is_local:
            from pyproj import CRS
            proj_wkt = ds.GetProjection()
            local_crs = CRS.from_wkt(proj_wkt) if proj_wkt else CRS.from_epsg(4326)
            # Reconstruct source grid based on file's native coordinate system
            x_raw_arr = gt[0] + gt[1] * (np.arange(nx_raw) + 0.5)
            y_raw_arr = gt[3] + gt[5] * (np.arange(ny_raw) + 0.5)
            lon_grid, lat_grid = np.meshgrid(x_raw_arr, y_raw_arr)
            
            # Reproject from native TIFF CRS directly to local UTM
            local_transformer = Transformer.from_crs(local_crs, f"EPSG:{epsg_utm}", always_xy=True)
            x_utm, y_utm = local_transformer.transform(lon_grid, lat_grid)
        else:
            lon_raw = gt[0] + gt[1] * (np.arange(nx_raw) + 0.5)
            lat_raw = gt[3] + gt[5] * (np.arange(ny_raw) + 0.5)
            lon_grid, lat_grid = np.meshgrid(lon_raw, lat_raw)
            x_utm, y_utm = transformer.transform(lon_grid, lat_grid)

        ds = None  # close

    # --- Shift to target domain source-centred system -----------------------
    x_utm -= src_x
    y_utm -= src_y

    # --- Resample onto regular metric grid ----------------------------------
    half = size_m / 2.0
    n_cells = int(round(size_m / resolution_m))
    x_new = np.linspace(-half, half, n_cells + 1)
    y_new = np.linspace(-half, half, n_cells + 1)

    # RegularGridInterpolator requires monotonic axes coordinates
    row_coords = y_utm[:, 0]
    col_coords = x_utm[0, :]

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

    # Gap filling for out of bound edges or NaN points
    nan_mask = np.isnan(z_resampled)
    if nan_mask.any():
        from scipy.ndimage import distance_transform_edt
        _, idx = distance_transform_edt(nan_mask, return_indices=True)
        z_resampled[nan_mask] = z_resampled[idx[0][nan_mask], idx[1][nan_mask]]

    z_resampled = np.round(z_resampled, 2)
    x_new = np.round(x_new, 2)
    y_new = np.round(y_new, 2)

    flat = z_resampled.ravel()
    zmin = np.sort(np.unique(flat))[1] if np.unique(flat).size > 1 else flat[0]
    z_resampled[z_resampled < zmin] = zmin

    return x_new, y_new, z_resampled, float(zmin)


# ---------------------------------------------------------------------------
# Multi-resolution convenience wrapper
# ---------------------------------------------------------------------------

def get_terrain(
    lat: float,
    lon: float,
    size_m: float,
    output_file: str,
    resolutions: Optional[list[dict]] = None,
    local_tif: Optional[str] = None,
    cache_dir: Optional[str] = None,
) -> None:
    if resolutions is None:
        half = size_m / 2.0
        resolutions = [
            {"resolution": 30, "lower_limit": half * 0.90, "upper_limit": None},
            {"resolution": 10, "lower_limit": half * 0.30, "upper_limit": half * 0.95},
            {"resolution": 5,  "lower_limit": half * 0.10, "upper_limit": half * 0.33},
            {"resolution": 2,  "lower_limit": None,        "upper_limit": half * 0.11},
        ]

    combined_zmin = math.inf
    grids: list[dict] = []
    
    for case in resolutions:
        res = case["resolution"]
        print(f"Processing grid at resolution: {res} m …")
        
        # Call the updated configuration handler
        x, y, z, zmin = load_terrain_grid(
            lat=lat, 
            lon=lon, 
            size_m=size_m, 
            resolution_m=res, 
            local_tif=local_tif, 
            cache_dir=cache_dir
        )
        combined_zmin = min(combined_zmin, zmin)
        grids.append({"x": x, "y": y, "z": z, "case": case})

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
# Main CLI Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Download SRTM1 terrain or read local TIFF using parameters mapped from an FDS mesh file."
    )
    parser.add_argument("lat",  type=float, help="Latitude of domain centre (°)")
    parser.add_argument("lon",  type=float, help="Longitude of domain centre (°)")
    
    parser.add_argument("--size", type=float, default=None, help="Domain side length (m) [Ignored if --mesh-file is passed]")
    parser.add_argument("-m", "--mesh-file", default=None, help="Path to your FDS mesh.txt file")
    parser.add_argument("-o", "--output", default="terrain.txt", help="Output FDS file")
    parser.add_argument("--cache-dir", default=None, help="Elevation cache directory")
    
    # NEW ARGUMENT: Local high-resolution terrain file
    parser.add_argument("--local-tif", default=None, help="Path to a local high-res .tif file (Used for resolutions <= 25m)")
    
    args = parser.parse_args()

    if args.mesh_file:
        print(f"Parsing FDS meshes from '{args.mesh_file}'...")
        domain_size, final_resolutions = parse_mesh_file(args.mesh_file)
        print(f"Calculated Domain Size: {domain_size} m")
        print("Generated Resolution Scheme:")
        for r in final_resolutions:
            print(f"  - {r['resolution']} m | Lower Limit: {r['lower_limit']} | Upper Limit: {r['upper_limit']}")
    else:
        if args.size is None:
            parser.error("You must provide either an explicit 'size' value or reference a file via --mesh-file (-m)")
        domain_size = args.size
        final_resolutions = None

    print("Starting terrain processor...")
    get_terrain(
        lat=args.lat, 
        lon=args.lon, 
        size_m=domain_size, 
        output_file=args.output, 
        resolutions=final_resolutions, 
        local_tif=args.local_tif,
        cache_dir=args.cache_dir
    )
    print(f"Process complete! Checked for file at: {os.path.abspath(args.output)}")
