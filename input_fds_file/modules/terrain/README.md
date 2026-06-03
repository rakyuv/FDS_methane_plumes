# srtm_to_fds.py

Downloads or reads elevation data and converts it into FDS `&OBST` terrain
cards for multi-resolution domains. Designed to be used either as a standalone
CLI tool or imported as a module by `build_fds.py`.

---

## Overview

FDS terrain is represented as a stack of solid `&OBST` blocks, one per grid
cell, rising from a common floor elevation (`zmin`) up to the terrain surface.
This script handles the full pipeline:

1. Determine the domain size and resolution tiers from a mesh file or manual input
2. Load elevation data — from a local GeoTIFF if available, otherwise download SRTM1 automatically
3. Reproject and resample to a metric grid centred on the source point
4. Write `&OBST` cards organised into concentric resolution rings

---

## Elevation data sources

| Source | When used | Resolution |
|---|---|---|
| Local GeoTIFF (`.tif`) | When `--local-tif` is provided and target resolution ≤ 30 m | Whatever the file contains — typically LiDAR at 1–5 m |
| SRTM1 (auto-download) | When no local file is provided, or resolution > 30 m | ~30 m native, resampled to target |

The local file takes priority for fine resolutions. SRTM1 is used as a fallback
for coarser rings where its 30 m native resolution is sufficient. Any CRS is
supported for local files — the script reprojects to UTM automatically.

### When to use a local GeoTIFF

SRTM1 at 30 m is adequate for the outer coarse rings of a typical FDS domain.
For the inner high-resolution rings — where cell sizes are 1 m, 3 m, or 9 m —
a higher-quality source is needed. LiDAR-derived terrain models (DTM/DSM) are
the standard choice where available, typically at 1 m native resolution.

LiDAR data is distributed as point cloud files (`.las` / `.laz`), which must be
preprocessed into a GeoTIFF before being passed to this script via `--local-tif`.
See [`las_to_tif.md`](las_to_tif.md) for the full preparation workflow.

### Preparing a LiDAR GeoTIFF (summary)

The conversion from `.laz` to a usable `.tif` involves four steps. Full
commands and pipeline files are documented in [`las_to_tif.md`](las_to_tif.md).

**1. Download LiDAR tiles**
LiDAR datasets are country-specific. For France, tiles are available from the
IGN GeoServices LiDAR HD portal as `.laz` files.

**2. Merge and crop (LAStools + PDAL)**
LiDAR tiles are large and often span multiple files. Use `lasmerge` to combine
adjacent tiles, then a PDAL crop pipeline to clip to your area of interest:

```bash
lasmerge -i tile1.laz tile2.laz -o merged.laz
pdal pipeline crop_pipeline.json   # bounds set to your domain extent
```

**3. Filter by point class (LAStools)**
LiDAR point clouds contain multiple surface classes. Filter to the classes
relevant to your simulation before rasterising:

| Class | Description | Typical use |
|---|---|---|
| 2 | Ground | Bare-earth terrain (DTM) |
| 3 | Short vegetation | Surface model with low cover |
| 4 | Medium vegetation | Surface model with medium cover |
| 5 | Tall vegetation | Surface model with tall cover |
| 6 | Buildings | Urban terrain |

For a terrain model that includes ground, buildings and vegetation up to medium
height:

```bash
las2las64 -i cropped.laz -o filtered.laz -keep_class 2 -keep_class 3 -keep_class 4 -keep_class 6
```

**4. Rasterise to GeoTIFF (PDAL + GDAL)**
Convert the filtered point cloud to a raster at the desired resolution using
PDAL's `writers.gdal` with IDW interpolation, then optionally resample to a
coarser target resolution with `gdalwarp`:

```bash
pdal pipeline pipeline.json          # produces output_dsm.tif at 1 m
gdalwarp -tr 2 2 -r lanczos output_dsm.tif terrain_2m.tif   # resample to 2 m
```

The resulting `.tif` file is passed directly to this script via `--local-tif`.
No reprojection or renaming is required — the script reads the CRS from the
file metadata and handles all coordinate transformations internally.

---

## Requirements

```bash
pip install numpy scipy pyproj gdal
```

For SRTM1 auto-download, the `elevation` package and GDAL command-line tools
are also required:

```bash
pip install elevation
```

---

## Usage

### As a standalone CLI

**Using a mesh file to derive domain and resolution automatically:**
```bash
python srtm_to_fds.py 49.583 18.441 --mesh-file mesh.txt -o terrain.txt
```

**Using a manual domain size:**
```bash
python srtm_to_fds.py 49.583 18.441 --size 5670 -o terrain.txt
```

**With a local high-resolution GeoTIFF:**
```bash
python srtm_to_fds.py 49.583 18.441 --mesh-file mesh.txt --local-tif lidar.tif -o terrain.txt
```

### As an imported module

```python
from srtm_to_fds import get_terrain, parse_mesh_file

domain_size, terrain_resolutions = parse_mesh_file("mesh.txt")

get_terrain(
    lat         = 49.583,
    lon         = 18.441,
    size_m      = domain_size,
    output_file = "terrain.txt",
    resolutions = terrain_resolutions,
    local_tif   = None,        # or "lidar.tif" for high-res local data
)
```

---

## CLI arguments

| Argument | Required | Description |
|---|---|---|
| `lat` | Yes | Latitude of the domain centre in decimal degrees |
| `lon` | Yes | Longitude of the domain centre in decimal degrees |
| `--mesh-file` / `-m` | One of these two | Path to an FDS `mesh.txt` file — domain size and resolution tiers are derived automatically |
| `--size` | One of these two | Domain side length in metres — used only when no mesh file is provided; resolution tiers fall back to script defaults |
| `--local-tif` | No | Path to a local high-resolution `.tif` file. Used for resolution tiers ≤ 30 m when provided; coarser tiers still use SRTM1 |
| `--output` / `-o` | No | Output file path (default: `terrain.txt`) |
| `--cache-dir` | No | Directory for the elevation package's SRTM tile cache |

---

## How resolution tiers work

The domain is divided into concentric hollow square rings, each served by a
different resolution. Every `&OBST` card is written only if its grid cell falls
within the ring assigned to that resolution — neither inside the inner boundary
nor outside the outer boundary.

| Parameter | Meaning |
|---|---|
| `lower_limit` | Half-width of the inner exclusion zone. Grid cells closer to the origin than this belong to a finer ring. `None` means no inner hole — this tier covers the centre. |
| `upper_limit` | Half-width of the outer clipping boundary. Grid cells further from the origin than this belong to a coarser ring. `None` means no outer cap — this tier covers everything outward. |

The limits are checked against both X and Y independently using a square
(Chebyshev) metric, consistent with the square mesh topology used by FDS.

### Derived from mesh file

When `--mesh-file` is supplied, `parse_mesh_file()` reads the `&MESH` cards
and reconstructs the resolution tiers automatically by grouping meshes by
their computed cell size and measuring the spatial extent of each group. This
ensures the terrain rings align exactly with the mesh resolution transitions.

### Default fallback (no mesh file)

When only `--size` is given, four default tiers are used:

| Resolution | Lower limit | Upper limit |
|---|---|---|
| 30 m | 90% of half-domain | None (outermost) |
| 10 m | 30% of half-domain | 95% of half-domain |
| 5 m | 10% of half-domain | 33% of half-domain |
| 2 m | None (centre) | 11% of half-domain |

---

## Output format

`terrain.txt` contains a comment header followed by `&OBST` namelists grouped
by resolution tier:

```
! Terrain generated by srtm_to_fds.py
! Centre: lat=49.583, lon=18.441  |  Domain: 5670 m
! zmin (floor) = 247.00 m

Terrain 27.00 m
&OBST XB=-2835.00,-2808.00,-2835.00,-2808.00,247.00,312.45/
&OBST XB=-2808.00,-2781.00,-2835.00,-2808.00,247.00,309.10/
...

Terrain 9.00 m
&OBST XB=-1215.00,-1206.00,-1215.00,-1206.00,247.00,298.70/
...
```

Each `&OBST` block spans one grid cell in X and Y, from `zmin` (the common
floor elevation) up to the terrain surface elevation at that cell. The floor
`zmin` is the second-lowest unique elevation found across all resolution tiers,
which avoids using an outlier minimum while still grounding the terrain.

---

## Coordinate system

The source point (`lat`, `lon`) is projected to UTM and used as the origin
`(0, 0)` of the FDS domain. All `&OBST` coordinates are in metres relative
to this origin, consistent with the mesh generator and `build_fds.py`.

UTM zone is determined automatically from the longitude. Hemisphere
(north/south) is determined from the latitude.

---

## Integration with build_fds.py

When called from `build_fds.py`, all inputs are derived automatically:

- `lat` and `lon` come from the shared `LAT` / `LON` parameter block
- `domain_size` and `terrain_resolutions` come from `parse_mesh_file("mesh.txt")`,
  which is called immediately after the mesh generator writes its output
- `local_tif` is set by the `LOCAL_TIF` parameter (`None` by default)

No manual size or resolution configuration is needed — the terrain always
matches the mesh exactly.

---

## Notes

- The output file is always overwritten on each run.
- SRTM1 tiles are cached by the `elevation` package. Subsequent runs over the
  same area reuse the cached tiles and do not re-download.
- NaN gaps in the elevation data (e.g. at the edge of a tile) are filled using
  nearest-neighbour propagation before writing.
- Local GeoTIFF files can be in any projected or geographic CRS — the script
  reads the CRS from the file metadata and reprojects to UTM automatically.
- For LiDAR data preparation (`.las` / `.laz` → `.tif`) or SRTM1 manual
  download and conversion steps, refer to the associated preprocessing
  documentation.
