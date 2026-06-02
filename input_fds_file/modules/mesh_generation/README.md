# FDS Mesh Generator

A Python tool for generating multi-resolution **Fire Dynamics Simulator (FDS)** mesh configurations. It produces nested mesh domains with geometrically increasing cell sizes — ideal for large-scale fire or atmospheric dispersion simulations where fine resolution is needed near the source and coarser resolution suffices at the boundaries.

---

## Features

- **Multi-resolution nested meshes** — generates concentric mesh domains, each at 3× the resolution of the previous
- **Non-overlapping boundary strips** — top, bottom, left, and right boundary meshes are computed explicitly to avoid mesh overlap
- **Z-domain expansion** — interior vertical domain grows with each resolution step
- **Constant-resolution boundary layers** — optional outer layers at fixed resolution for domain padding
- **MPI process assignment** — automatically assigns `MPI_PROCESS` indices based on a configurable division factor
- **Mesh alignment checking** — outputs `CHECK_MESH_ALIGNMENT=T` on every mesh line

---

## Requirements

- Python 3.7+
- NumPy

Install dependencies:

```bash
pip install numpy
```

---

## Usage

```bash
python fds_mesh_generator.py [OPTIONS]
```

### Options

| Argument | Type | Default | Description |
|---|---|---|---|
| `--res` | float | `1.0` | Starting (finest) resolution in metres |
| `--steps` | int | `4` | Number of resolution steps |
| `--z_min` | int | `247` | Minimum Z coordinate of the domain |
| `--mpi` | int | `1` | MPI division factor (meshes per MPI process) |
| `--layers` | int | `2` | Number of constant-resolution boundary layers |

### Examples

Generate a default 4-step mesh starting at 1 m resolution:

```bash
python fds_mesh_generator.py
```

Generate a fine 0.5 m mesh with 3 resolution steps and 4 MPI processes:

```bash
python fds_mesh_generator.py --res 0.5 --steps 3 --mpi 4
```

Generate a coarser mesh with extra boundary padding:

```bash
python fds_mesh_generator.py --res 2.0 --steps 3 --layers 4 --z_min 300
```

---

## Output

The script writes a `.fds` file named after the run parameters, e.g.:

```
fds_res_1.0_steps_4_layers_2.fds
```

Each line follows the FDS `&MESH` namelist format:

```
&MESH ID = 'mesh0', IJK = 30, 30, 30, XB = -45.00, 45.00, -45.00, 45.00, 247.00, 1147.00, MPI_PROCESS=0, CHECK_MESH_ALIGNMENT=T/
```

Comment lines (`#`) are inserted to label each resolution level and boundary section for readability.

---

## How It Works

### Resolution Steps

Each step multiplies the cell size by 3. For `--res 1.0 --steps 4`, the resolutions are:

```
Step 0: 1 m  (finest, central domain)
Step 1: 3 m  (surrounding boundary ring)
Step 2: 9 m
Step 3: 27 m (coarsest)
```

### Domain Sizing

The horizontal domain size at each step is:

```
domain_size = resolution × domain_factor (default 90)
```

So a 1 m resolution produces a 90 m × 90 m central domain; a 3 m resolution produces a 270 m × 270 m outer ring; and so on.

### Mesh Layout (single step)

```
┌─────────────────────────────────┐
│         Top boundary            │
├──────┬──────────────────┬───────┤
│      │                  │       │
│ Left │  Previous domain │ Right │
│      │                  │       │
├──────┴──────────────────┴───────┤
│        Bottom boundary          │
└─────────────────────────────────┘
```

### Constant Boundary Layers

After the resolution steps, additional layers of uniform-resolution meshes can be added around the outermost domain using `--layers`. Each layer extends the domain by one mesh cell width in all four horizontal directions.

---

## Class Reference

### `FDSMeshGenerator(mpi_division_factor=1, ijk=(30, 30, 30))`

| Method | Description |
|---|---|
| `generate_fds_meshes(...)` | Writes `&MESH` lines for a single rectangular region |
| `generate_all_resolutions(...)` | Orchestrates the full nested multi-resolution domain |
| `generate_constant_resolution_boundaries(...)` | Appends constant-resolution outer boundary layers |

The class maintains a running `current_mesh_id` counter across all calls, ensuring globally unique mesh IDs across the entire file.

---

## License

MIT License. See `LICENSE` for details.
