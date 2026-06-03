[![DOI](https://zenodo.org/badge/1106056771.svg)](https://doi.org/10.5281/zenodo.20529870)
# FDS: CH₄ simulations

This repository contains everything needed to simulate a CH₄ plume using [Fire Dynamics Simulator (FDS)](https://pages.nist.gov/fds-smv/). The workflow is modular: each preprocessing step lives in its own script, all feeding into a single main code called build_fds_inputFile.py that generates the FDS input file from a shared parameter file.

# build_fds_inputFile.py

Automated FDS (Fire Dynamics Simulator) input file generator for atmospheric wind simulations over real terrain. Orchestrates three specialist modules to
produce a complete, ready-to-run `inputfile.fds` from a single parameter block.

---

## Overview

`build_fds.py` is the single entry point for the whole pipeline. You edit the
parameters block at the top, run the script, and get `inputfile.fds` out. The
three modules it drives are:

| Module | What it does | Output |
|---|---|---|
| `fds_mesh_generator.py` | Builds nested multi-resolution FDS mesh | `mesh.txt` |
| `era5_downloader.py` | Downloads ERA5 wind & temperature profiles | `era5_fds_ramp_<date>_<hour>UTC.txt`, `era5_single_levels.nc`, `era5_pressure_levels.nc` |
| `srtm_to_fds.py` | Downloads SRTM1 terrain or reads a local GeoTIFF | `terrain.txt` |

All files are written to the working directory (wherever you run the script from).

---

## Requirements

```
pip install cdsapi xarray netCDF4 numpy scipy pyproj elevation gdal
```

- A valid `~/.cdsapirc` file with your [CDS API key](https://cds.climate.copernicus.eu/api-how-to)
- GDAL command-line tools available on your system
- The four Python files in the same directory:
  - `build_fds.py`
  - `fds_mesh_generator.py`
  - `era5_downloader.py`
  - `srtm_to_fds.py`

---

## Usage

Edit the parameters block at the top of `build_fds.py`, then run:

```bash
python build_fds.py
```

---

## Parameters

All parameters live in the top section of `build_fds.py`. Nothing else needs
to be edited.

### Simulation identity

| Parameter | Type | Description |
|---|---|---|
| `CHID` | `str` | FDS character ID, used as the filename stem for all FDS outputs |
| `LAT` | `float` | Latitude of the domain centre in decimal degrees |
| `LON` | `float` | Longitude of the domain centre in decimal degrees |
| `NORTH_BEARING` | `int` | Rotation of the domain relative to north (degrees) |
| `LEVEL_SET_MODE` | `int` | FDS wind profile mode — `3` follows terrain |
| `THICKEN_OBSTRUCTIONS` | `str` | FDS flag, keep as `T` |

### Time

| Parameter | Type | Description |
|---|---|---|
| `START_DATE` | `str` | Simulation start date, `YYYY-MM-DD` |
| `START_TIME` | `str` | Simulation start time (UTC), `HH:MM:SS` |
| `SIM_DURATION_S` | `int` | Simulation duration in seconds |

### Mesh resolution

| Parameter | Type | Description |
|---|---|---|
| `HIGHEST_RESOLUTION` | `int` | Finest cell size in metres at the domain centre |
| `STEPS` | `int` | Number of resolution jumps outward (each step triples the cell size) |
| `LAYERS` | `int` | Number of constant-resolution outer boundary rings at the coarsest level |
| `Z_MIN` | `int` | Lowest Z coordinate in the domain (metres above sea level) |
| `MPI` | `int` | Number of meshes handled per MPI process |

### Boundary conditions

| Parameter | Type | Description |
|---|---|---|
| `LATERAL_SURF_ID` | `str` | Surface applied to XMIN, XMAX, YMIN, YMAX vents |
| `GROUND_SURF_ID` | `str` | Surface applied to the ZMIN vent and `&SURF` ground definition |
| `TOP_SURF_ID` | `str` | Surface applied to the ZMAX vent |

### Slice files

```python
SLCF_QUANTITIES = [
    {"QUANTITY": "TEMPERATURE",     "VECTOR": ".TRUE."},
    {"QUANTITY": "U-VELOCITY"},
    {"QUANTITY": "V-VELOCITY"},
    {"QUANTITY": "W-VELOCITY"},
    {"QUANTITY": "PRESSURE",        "VECTOR": ".TRUE."},
    {"QUANTITY": "VOLUME FRACTION", "SPEC_ID": "'METHANE'"},
]
```

Comment out any entry you do not need, or add new ones following the same
dictionary structure. All entries share the same `XB` spanning the full domain
extent derived automatically from the mesh.

### Terrain

| Parameter | Type | Description |
|---|---|---|
| `TERRAIN_FILE` | `str` | Output path for the terrain obstruction file |
| `LOCAL_TIF` | `str` or `None` | Path to a local high-resolution GeoTIFF. If `None`, SRTM1 data is downloaded automatically. Used for resolutions ≤ 30 m when provided |

---

## Pipeline steps

```
build_fds.py
│
├── Step 2   fds_mesh_generator.py  →  mesh.txt
│            Returns domain extents (x/y/z min-max) for use downstream
│
├── Step 2b  era5_downloader.py     →  era5_fds_ramp_<date>_<hour>UTC.txt
│            Returns T_2m, skin temperature, surface pressure
│
├── Step 2c  srtm_to_fds.py         →  terrain.txt
│            Reads mesh.txt to derive domain size and resolution tiers
│
└── Step 3   Assembles inputfile.fds from all of the above
```

### Section order in `inputfile.fds`

1. `&HEAD` — simulation identity
2. `&MESH` — all mesh definitions
3. `&TIME` — start date/time and duration
4. `&MISC` — TMPA (T_2m), P_INF (surface pressure), wind mode flags
5. `&GEOM` — geolocation
6. `&SURF` — ground surface with TMP_FRONT (skin temperature) and soil properties
7. `&WIND` + `&RAMP` — ERA5 wind speed, direction and temperature profiles
8. `&VENT` — boundary conditions on all six domain faces
9. `&SLCF` — slice file outputs
10. `&OBST` — terrain obstructions
11. `&DUMP` — output controls
12. `&TAIL`

---

## ERA5 wind profile

The ERA5 module produces three `&RAMP` profiles:

- **`spd`** — wind speed vs height, anchored at `Z_MIN + 10` m using the ERA5
  10 m wind, then pressure-level values above. Sorted to ensure monotonic Z.
- **`dir`** — wind direction vs height, same anchoring and sorting as speed.
- **`tmp_profile`** — temperature ratio `T(z) / T_2m` from pressure levels only
  (no fabricated surface anchor point).

The `&WIND` namelist references all three ramps and sets `SPEED` and
`DIRECTION` to the 10 m ERA5 values.

---

## Notes

- `Z_MIN` and `START_DATE`/`START_TIME` are shared automatically between the
  mesh generator, ERA5 downloader and terrain processor — no duplication.
- The domain extents used in `&SLCF` are derived directly from the mesh output,
  not from the input parameters, so they always reflect the actual generated
  domain.
- If `LOCAL_TIF = None` and no internet connection is available, the terrain
  step will fail. Pre-download SRTM tiles or provide a local GeoTIFF.
- All intermediate files (`mesh.txt`, `terrain.txt`, ERA5 NetCDF and RAMP files)
  are kept after the run and can be inspected independently.

## Acknowledgements

The core logic and algorithms of this repository were designed by the author. Generative AI tools (Gemini and Claude) were utilised to assist with Pythonic code optimization, formatting, and documentation.
