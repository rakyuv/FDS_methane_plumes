## Mesh design and HPC scaling

Designing the mesh requires balancing **spatial resolution**, **domain size**, and **available CPU cores**. Since each mesh in FDS runs on one MPI process, the total number of meshes equals the number of cores used.

### General strategy

The recommended approach is:

1. **Fix the number of grid points per mesh per direction** — 30 points per direction (`IJK = 30, 30, 30`) is a good practical choice. It keeps memory per core manageable and ensures efficient MPI communication.
2. **Choose your finest resolution** based on the near-source physics you need to resolve.
3. **Scale outward** by multiplying cell size by a factor of 3 at each nesting level — this ensures cell faces align cleanly at mesh boundaries.
4. **Count the total meshes** and verify it fits within your core budget.

The cell size at each level is:

```
cell_size = domain_extent_per_mesh / points_per_direction
```

For example, with 30 points per direction:

| Level | Mesh extent (x or y) | Cell size |
|---|---|---|
| 1 (finest) | 1.2 m | 0.04 m |
| 2 | 3.6 m | 0.12 m |
| 3 | 10.8 m | 0.36 m |
| 4 (coarsest) | 32.4 m | 1.08 m |

Each level covers a 3×3 horizontal tile of meshes around the inner domain, plus vertical stacking — giving roughly 27 meshes per resolution level in the inner nest, scaling outward.

---

### Example: `nearfield`

A single spatial resolution covering a small domain around the source.

- **Resolution:** 0.04 m
- **Mesh layout:** 27 meshes (3×3×3)
- **Total cores:** 27
- **Best suited for:** detailed near-source plume structure, short simulations

---

### Example: `largedomain`

Four nested spatial resolutions, covering the full plume extent from the source to the far field.

- **Resolutions:** 0.04 m → 0.12 m → 0.36 m → 1.08 m
- **Total meshes:** 153
- **Total cores:** 153
- **Best suited for:** full plume dispersion, emission quantification, comparison with observations

The nesting structure looks like this:

```
Resolution   Cell size   Domain extent (x,y)   Meshes
Level 1      0.04 m      ± 1.8 m               27
Level 2      0.12 m      ± 5.4 m               26
Level 3      0.36 m      ± 16.2 m              26
Level 4      1.08 m      ± 48.6 m / ± 81.0 m  74
─────────────────────────────────────────────────
Total                                          153
```

---

### Adapting to your HPC resources

The key constraint is the number of available cores. At [IDRIS](http://www.idris.fr), the examples here were designed to stay under 200 cores. To adapt:

- **Fewer cores available:** reduce the number of nesting levels, or shrink the outer domain extent. The inner nest resolution can be kept unchanged.
- **More cores available:** add a finer innermost level (multiply finest cell size by 1/3), or extend the outer domain further.
- **Rule of thumb:** keep `IJK = 30, 30, 30` fixed and adjust the number and size of meshes to fit your budget. Avoid going below 20 or above 50 points per direction — too few reduces accuracy, too many increases memory per core.

> For optimal MPI performance on most HPC systems, aim for a total cell count per mesh of around 27 000 (i.e. 30³). Larger meshes reduce communication overhead but increase memory pressure per core.
