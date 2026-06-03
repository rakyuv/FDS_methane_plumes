# fds_mesh_generator.py

Generates FDS `&MESH` configurations with nested, multi-resolution domains
centred on the origin. Designed to be used either as a standalone CLI tool
or imported as a module by `build_fds.py`.

---

## Concept

FDS simulations over large outdoor domains benefit from variable resolution:
fine cells near the area of interest, coarser cells further out. This script
builds that structure automatically as a set of concentric hollow square rings,
each three times coarser than the one inside it, plus optional constant-resolution
outer boundary layers.

```
┌─────────────────────────────┐
│  27 m  (coarsest, layer 2)  │
│  ┌───────────────────────┐  │
│  │  27 m  (layer 1)      │  │
│  │  ┌─────────────────┐  │  │
│  │  │  27 m  (step 4) │  │  │
│  │  │  ┌───────────┐  │  │  │
│  │  │  │  9 m      │  │  │  │
│  │  │  │  ┌─────┐  │  │  │  │
│  │  │  │  │ 3 m │  │  │  │  │
│  │  │  │  │ ┌─┐ │  │  │  │  │
│  │  │  │  │ │1m│ │  │  │  │  │
│  │  │  │  │ └─┘ │  │  │  │  │
│  │  │  │  └─────┘  │  │  │  │
│  │  │  └───────────┘  │  │  │
│  │  └─────────────────┘  │  │
│  └───────────────────────┘  │
└─────────────────────────────┘
```

Each resolution ring is a set of `&MESH` blocks that tile the annular region
between the inner and outer domain sizes for that step. The vertical extent
also grows with each resolution step.

---

## Usage

### As a standalone CLI

```bash
python fds_mesh_generator.py --res 1.0 --steps 4 --z_min 247 --mpi 1 --layers 2
```

Output is written to `mesh.txt` in the current directory.

### As an imported module

```python
from fds_mesh_generator import MeshConfig, run

config = MeshConfig(res=1.0, steps=4, z_min=247, mpi=1, layers=2)
result = run(config)

# result is a dict:
# {
#   "output" : "mesh.txt",
#   "x_min"  : -2835.0,
#   "x_max"  :  2835.0,
#   "y_min"  : -2835.0,
#   "y_max"  :  2835.0,
#   "z_min"  :  247.0,
#   "z_max"  :  337.0,
# }
```

The returned dict gives the full domain extents, which `build_fds.py` uses
to set `&SLCF` bounds and other domain-wide namelists.

---

## Parameters

### `MeshConfig` dataclass

| Parameter | Type | Default | Description |
|---|---|---|---|
| `res` | `float` | `1.0` | Finest cell size in metres at the domain centre |
| `steps` | `int` | `4` | Number of resolution jumps outward (each step triples `res`) |
| `z_min` | `int` | `247` | Lowest Z coordinate of the domain (metres above sea level) |
| `mpi` | `int` | `1` | Number of meshes assigned per MPI process |
| `layers` | `int` | `2` | Number of constant-resolution outer boundary rings at the coarsest level |
| `ijk` | `tuple` | `(30, 30, 30)` | Cell counts per mesh block in I, J, K |
| `output` | `str` | `"mesh.txt"` | Output file path |

### CLI flags

| Flag | Default | Description |
|---|---|---|
| `--res` | `1.0` | Starting resolution in metres |
| `--steps` | `4` | Number of resolution steps |
| `--z_min` | `247` | Minimum Z coordinate |
| `--mpi` | `1` | MPI division factor |
| `--layers` | `2` | Number of constant boundary layers |
| `--output` | `mesh.txt` | Output file path |

---

## How the domain is built

### Resolution steps

Starting from `res`, each step outward triples the cell size:

| Step | Resolution | Domain half-width | Z extent |
|---|---|---|---|
| 1 | `res × 1` | `res × 90 / 2` | `res × 30 × 3` |
| 2 | `res × 3` | `res × 270 / 2` | `res × 90 × 3` |
| 3 | `res × 9` | `res × 810 / 2` | `res × 270 × 3` |
| 4 | `res × 27` | `res × 2430 / 2` | `res × 810 × 3` |

With `res = 1.0` and `steps = 4`, the outermost resolution step reaches
±1215 m in X and Y.

The domain factor of 90 means each mesh block covers exactly `res × 90` metres
in X and Y with the default `ijk = (30, 30, 30)`, giving 3 cell-widths of 30
cells each.

### Constant boundary layers

After the last resolution step, `layers` additional rings are added at the same
(coarsest) resolution, each one mesh-block wide (`final_res × ijk[0]`). These
expand the domain further without introducing a new resolution tier and are
useful for absorbing boundary effects.

With `res = 1.0`, `steps = 4`, and `layers = 2`:
- Coarsest resolution: 27 m
- Each boundary layer width: 27 × 30 = 810 m
- Total domain half-width after layers: 1215 + 810 + 810 = **2835 m**

### Vertical extent

The vertical domain grows with each step because `dz = current_res × ijk[2]`
and each step covers `3 × dz` vertically. With `res = 1.0` and `steps = 4`:

| Step | `dz` | Z height above `z_min` |
|---|---|---|
| 1 | 30 m | 90 m |
| 2 | 90 m | 270 m |
| 3 | 270 m | 810 m |
| 4 | 810 m | **2430 m** |

### MPI assignment

Each mesh block is assigned an `MPI_PROCESS` index equal to
`mesh_id // mpi`. With `mpi = 1` every mesh runs on a separate process.
Increase `mpi` to batch multiple meshes onto the same process when the
total mesh count exceeds your available MPI ranks.

---

## Output format

`mesh.txt` contains raw FDS `&MESH` namelists, one per line, with comment
headers marking each resolution tier:

```
# 1 m X/Y Resolution
&MESH ID = 'mesh0', IJK = 30, 30, 30, XB = -45.00, -15.00, -45.00, -15.00, 247.00, 277.00, MPI_PROCESS=0, CHECK_MESH_ALIGNMENT=T/
...

----------------------------------

# 3 m X/Y Resolution
# Top Boundary
&MESH ID = 'mesh27', IJK = 30, 30, 30, XB = -135.00, -45.00, 45.00, 135.00, 247.00, 337.00, MPI_PROCESS=27, CHECK_MESH_ALIGNMENT=T/
...
```

`CHECK_MESH_ALIGNMENT=T` is written on every line so FDS validates that
adjacent meshes share coincident cell boundaries at resolution transitions.

---

## Notes

- All meshes are centred on the origin `(0, 0)`. The simulation source point
  should be placed at the origin in the FDS input file.
- `ijk = (30, 30, 30)` is the recommended default. Changing it will rescale
  the physical size of every mesh block and alter the domain extents
  proportionally.
- The output file is always overwritten on each run.
- When used via `build_fds.py`, the `output` field defaults to `"mesh.txt"`
  and is written to the current working directory alongside all other
  generated files.
