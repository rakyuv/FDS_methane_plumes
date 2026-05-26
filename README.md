FDS: CH₄ simulations

This repository contains everything needed to simulate a CH₄ plume using [Fire Dynamics Simulator (FDS)](https://pages.nist.gov/fds-smv/). The workflow is modular: each preprocessing step lives in its own script, all feeding into a single main code that generates the FDS input file from a shared parameter file.

If you use this tutorial as part of a publication, please cite:

> Yuvaraj, R., Lauvaux, T., Abdallah, C., Ciais, P., Akani Guery, J., Bonne, J.L., Groshenry, A., Hoang, N.M. and Joly, L., 2026. High-Resolution Modeling of Methane Plumes: Validation and Sensitivity Experiments to Explore Emission Quantification Approaches. *Environmental Science & Technology*.

## Repository structure
```
.
├── params.txt                 # All user-defined parameters (edit this before running)
├── input_fds_file.py          # Main script — generates the FDS input file
├── era5_download.py           # Module: download and convert ERA5 meteorological data
├── terrain_fetch.py           # Module: fetch and convert terrain topology data
├── postprocessing/
│   └── slcf_to_netcdf.py      # Convert FDS .slcf output files to NetCDF
└── README.md

```

## Workflow overview
```
params.txt
    │
    ▼
input_fds_file.py
    ├── era5_download()    →  met_surface.txt, met_pressure.txt
    ├── terrain_fetch()    →  terrain.txt
    └── [ future modules ]
    │
    ▼
 simulation.fds
    │
    ▼
 FDS run  →  *.sf              # FDS saves slices in SLCF format
    │
    ▼
 slcf_to_netcdf.py  →  *.nc    # .sf files can easily be converted to .nc files
```


## Quick start

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> Python ≥ 3.9 recommended. Key dependencies: `cdsapi`, `cfgrib`, `xarray`, `numpy`, `rasterio`.

### 3. Edit `params.txt`

All simulation parameters are centralized in `params.txt`. Open it and set at minimum:
Domain
lon_min     = 2.5
lon_max     = 3.0
lat_min     = 48.5
lat_max     = 49.0
start_date  = 2024-06-01
start_time  = 12:00:00
sim_duration_s = 3600
Source
emission_rate_kg_s = 0.05
source_lon  = 2.75
source_lat  = 48.75
source_height_m = 1.0
Resolution
dx_m = 5
dy_m = 5
dz_m = 5

A full annotated description of every parameter is in [`params.txt`](params.txt).

### 4. Generate the FDS input file

```bash
python input_fds_file.py
```

This calls all preprocessing modules internally — ERA5 download, terrain fetch, and any others — and produces `simulation.fds` directly. No need to run the modules separately.

> You need a [CDS API key](https://cds.climate.copernicus.eu/api-how-to) configured in `~/.cdsapirc` for the ERA5 download step.
> Module descriptions table — update the description column to reflect that these are called internally, not run standalone:

| Script | Role | Inputs | Outputs |
|---|---|---|---|
| `era5_download.py` | Called by main — downloads ERA5 met fields | `params.txt` | `met_surface.txt`, `met_pressure.txt` |
| `terrain_fetch.py` | Called by main — fetches and converts DEM | `params.txt` | `terrain.txt` |
| `input_fds_file.py` | **Main script** — calls all modules and writes FDS input | `params.txt` | `simulation.fds` |
| `slcf_to_netcdf.py` | Postprocessing — converts FDS slice output to NetCDF | `*.slcf` | `*.nc` |

> All modules are imported and called automatically by `input_fds_file.py`. 
> They can still be imported individually for debugging or development purposes.
### 5. Generate the FDS input file

```bash
python input_fds_file.py
```

Reads `params.txt`, `met_surface.txt`, `met_pressure.txt`, and `terrain.txt` to produce `simulation.fds`.

### 6. Run FDS

```bash
fds simulation.fds
```

Refer to the [FDS user guide](https://pages.nist.gov/fds-smv/) for parallelisation and HPC submission options.

### 7. Postprocessing (convert `.slcf` to NetCDF)

```bash
python postprocessing/slcf_to_netcdf.py
```

Converts all `.slcf` slice files produced by FDS into CF-compliant `.nc` files, ready for analysis in Python or NCO/CDO.

---

## Module descriptions

| Script | Role | Inputs | Outputs |
|---|---|---|---|
| `era5_download.py` | Download ERA5 met fields and format for FDS | `params.txt` | `met_surface.txt`, `met_pressure.txt` |
| `terrain_fetch.py` | Fetch DEM and convert to FDS terrain format | `params.txt` | `terrain.txt` |
| `input_fds_file.py` | Assemble and write the FDS input file | `params.txt` + all `.txt` above | `simulation.fds` |
| `slcf_to_netcdf.py` | Convert FDS slice output to NetCDF | `*.slcf` | `*.nc` |

---
## Notes

- All modules are designed to be run independently for testing before calling the main script. They are imported and called automatically by `input_fds_file.py`. 
- `params.txt` is the single source of truth — no hardcoded paths or values should appear elsewhere.
- Postprocessing (NetCDF conversion) is documented in [`postprocessing/README.md`](postprocessing/README.md) *(to be added)*.

---

## License
