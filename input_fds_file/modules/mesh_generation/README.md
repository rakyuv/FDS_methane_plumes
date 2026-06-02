# FDS Mesh Generator

A Python module for generating multi-resolution **Fire Dynamics Simulator (FDS)** mesh configurations. It produces nested mesh domains with geometrically increasing cell sizes — ideal for large-scale fire or atmospheric dispersion simulations where fine resolution is needed near the source and coarser resolution suffices at the boundaries.

The module writes its output to **`mesh.txt`**, which is intended to be consumed by a separate script that assembles the full FDS input file.

---

## Features

- **Importable module** — use `MeshConfig` and `run()` directly from any other Python script
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

### As a module (recommended)

Import `MeshConfig` and `run()` from your FDS builder or any other script:

```python
from fds_mesh_generator import MeshConfig, run

# Override only the parameters you need; all others fall back to defaults
config = MeshConfig(res=0.5, steps=3, z_min=300, mpi=4, layers=2)
run(config)
# → writes mesh.txt
```

`run()` returns the path of the written file (`config.output`, default `"mesh.txt"`), so you can chain it directly into your FDS file builder:

```python
from fds_mesh_generator import MeshConfig, run

mesh_path = run(MeshConfig(res=1.0, steps=4))

with open(mesh_path) as f:
    mesh_block = f.read()

# ... assemble the rest of the FDS input file
```

### As a standalone CLI script

```bash
python fds_mesh_generator.py [OPTIONS]
```

#### Options

| Argument | Type | Default | Description |
|---|---|---|---|
| `--res` | float | `1.0` | Starting (finest) resolution in metres |
| `--steps` | int | `4` | Number of resolution steps |
| `--z_min` | int | `247` | Minimum Z coordinate of the domain |
| `--mpi` | int | `1` | MPI division factor (meshes per MPI process) |
| `--layers` | int | `2` | Number of constant-resolution boundary layers |
| `--output` | str | `mesh.txt` | Output file path |

#### Examples

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

Both usage modes write to **`mesh.txt`** (or the path set in `MeshConfig.output`). This file is not a complete FDS input — it contains only the `&MESH` block, ready to be embedded into a larger FDS file by your builder script.

Each line follows the FDS `&MESH` namelist format:

```
&MESH ID = 'mesh0', IJK = 30, 30, 30, XB = -45.00, 45.00, -45.00, 45.00, 247.00, 1147.00, MPI_PROCESS=0, CHECK_MESH_ALIGNMENT=T/
```

Comment lines (`#`) and section separators are inserted to label each resolution level and boundary strip for readability.

---

## How It Works

### Resolution Steps

Each step multiplies the cell size by 3. For `--res 1.0 --steps 4`, the resolutions are:

```
Step 0:  1 m  (finest, central domain)
Step 1:  3 m  (surrounding boundary ring)
Step 2:  9 m
Step 3: 27 m  (coarsest)
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

After the resolution steps, additional layers of uniform-resolution meshes can be added around the outermost domain using `--layers` (or `MeshConfig.layers`). Each layer extends the domain by one mesh cell width in all four horizontal directions.

---

## API Reference

### `MeshConfig`

A dataclass holding all generation parameters. All fields have defaults so you only need to specify what differs from the baseline.

| Field | Type | Default | Description |
|---|---|---|---|
| `res` | float | `1.0` | Starting (finest) resolution in metres |
| `steps` | int | `4` | Number of resolution steps |
| `z_min` | int | `247` | Minimum Z coordinate |
| `mpi` | int | `1` | MPI division factor |
| `layers` | int | `2` | Number of constant boundary layers |
| `ijk` | tuple | `(30, 30, 30)` | Cell counts per mesh in I, J, K |
| `output` | str | `"mesh.txt"` | Output file path |

### `run(config: MeshConfig = None) -> str`

Executes the full mesh generation pipeline and writes the result to `config.output`. Returns the output file path. If `config` is omitted, all defaults are used.

### `FDSMeshGenerator(config: MeshConfig)`

The underlying class, if you need finer control. Maintains a running `current_mesh_id` counter across all calls to ensure globally unique mesh IDs.

| Method | Description |
|---|---|
| `generate_fds_meshes(fh, resolution, x_min, x_max, y_min, y_max, z_min, z_max)` | Tiles a rectangular region with `&MESH` lines |
| `generate_all_resolutions(fh)` | Builds the full nested multi-resolution domain |
| `generate_constant_resolution_boundaries(fh, resolution, final_domain_size)` | Appends constant-resolution outer rings |

---

## License

MIT License. See `LICENSE` for details.
