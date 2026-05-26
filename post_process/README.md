# Postprocessing: SLCF to NetCDF conversion

This folder contains two scripts to convert FDS slice files (`.slcf`) into NetCDF (`.nc`) files. Both scripts converts the outputs from each mesh into a single file per variable, interpolating to a common spatial grid.

---

## Scripts

### `slcf_to_netcdf_all_time_steps.py`

Converts the full time series of `.slcf` files into NetCDF, with dimensions organized as `variable(t, z, y, x)`.

Since FDS subdivides the domain into separate meshes, each `.slcf` file corresponds to one mesh. This script merges all meshes and interpolates them to the **highest resolution grid** present in the simulation.

> ⚠️ **Important:** If your simulation uses multiple spatial resolutions, all data is interpolated to the finest grid. This can result in very large `.nc` files. In that case, use `slcf_to_netcdf_discrete_time_steps.py` instead.

**Best suited for:**
- Simulations with one or two spatial resolutions
- Short simulations with a manageable number of time steps
- Cases where the full time series is needed for analysis

**Usage:**
```bash
python slcf_to_netcdf_all_time_steps.py
```

---

### `slcf_to_netcdf_discrete_time_steps.py`

Converts `.slcf` files to NetCDF at **selected time steps only**, with full control over which spatial resolutions to include and the output grid resolution.

This is the recommended script when dealing with large simulations spanning multiple spatial resolutions and many time steps.

**Key features:**
- Select specific time steps to extract, rather than the full time series
- Choose which spatial resolutions to include in the output (e.g. only the 1 m and 3 m meshes, skipping coarser ones)
- Set the target output resolution independently — for example, interpolate everything to 27 m to cover the full domain at reduced file size

**Example scenarios:**

| Simulation grids | Goal | Configuration |
|---|---|---|
| 1 m, 3 m, 9 m, 27 m | High-detail inner domain | Include 1 m + 3 m, interpolate to 1 m |
| 1 m, 3 m, 9 m, 27 m | Mid-range domain | Include 3 m + 9 m, interpolate to 3 m |
| 1 m, 3 m, 9 m, 27 m | Full domain, compact file | Include all, interpolate to 27 m |

**Usage:**

Run with default parameters:
```bash
python slcf_to_netcdf_discrete_time_steps.py
```

Override any default by passing arguments:
```bash
python slcf_to_netcdf_discrete_time_steps.py --resolutions 1 3 --target_res 1 --time_steps 0 100 200
```

Run with `--help` to see all available options and their defaults:
```bash
python slcf_to_netcdf_discrete_time_steps.py --help
```

---

## Output format

Both scripts produce NetCDF files with the following structure:

```
variable(t, z, y, x)
```

- `t` — time steps (all steps, or selected discrete steps)
- `z` — vertical levels
- `y`, `x` — horizontal grid, interpolated to the target resolution

One `.nc` file is produced per variable.

---

## Parameters

- `slcf_to_netcdf_all_time_steps.py` doesn't need any parameters to be set. It converts the `.sf` files from each mesh to a separate `.nc` file, for all time-steps for the whole domain
- `slcf_to_netcdf_discrete_time_steps.py` comes with sensible defaults built in. Any parameter can be overridden at the command line as an argument — run `--help` for the full list.

---

## Notes

- Interpolation is performed to a regular grid. Ensure the target resolution is consistent with your analysis needs before running.
- For very large simulations, running `slcf_to_netcdf_discrete_time_steps.py` with a coarse target resolution first is a good way to check the output before committing to a full high-resolution conversion.
