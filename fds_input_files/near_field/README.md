# CH4 Release from a Point Source — FDS Simulation

## Overview

This repository contains an [FDS (Fire Dynamics Simulator)](https://pages.nist.gov/fds-smv/) input file for simulating the atmospheric dispersion of methane (CH₄) released from a point source. The simulation uses real terrain data and wind profile measurements to model the transport and dilution of the gas plume in a geographically grounded outdoor environment.

**Case ID:** `ch4_release`  
**Simulation duration:** 2400 s (~40 min)  
**Origin coordinates:** 43.4126208°N, 0.6428329°W

---

## Physical Setup

### Source

A small obstruction (0.16 m × 0.16 m × 1.5 m tall) represents the release stack. Methane is injected through a vent at the top of this obstruction:

- **Mass flux:** 17.22 kg/m²/s of CH₄
- **Stack top elevation:** 96.61 m (absolute)
- **Location:** domain origin (x = 0, y = 0)

### Atmosphere

| Parameter | Value |
|---|---|
| Ambient temperature | 16.72 °C |
| Ground temperature | 15.72 °C |
| Ground roughness length | 0.978 m |

### Wind Profile

The wind speed and direction follow measured vertical profiles (defined via `RAMP`):

| Height (m AGL) | Speed (m/s) | Direction (°) |
|---|---|---|
| 2.5 | 1.79 | 1.15 |
| 11.0 | 3.30 | 358.66 |
| 16.0 | 3.38 | 357.34 |
| 21.0 | 3.51 | 358.20 |
| 26.0 | 3.66 | 359.21 |
| 31.0 | 3.81 | 359.23 |
| 39.0 | 4.00 | 0.56 |

The wind blows approximately from the south (~0° North), with a slight veering near the surface.

### Terrain

- `LEVEL_SET_MODE = 3`: wind field adapts to terrain topography; no fire.
- `THICKEN_OBSTRUCTIONS = T`: ensures terrain obstructions span at least one full grid cell. 
The terrain information is added through `OBST`, and the process is explained 

---

## Computational Domain & Mesh

The domain uses a **multi-level nested mesh** strategy (153 meshes total, each 30×30×30 cells) to achieve high resolution near the source while extending to a large outer domain for accurate far-field dispersion:

| Level | XY extent | Z extent | Resolution |
|---|---|---|---|
| **Inner (fine)** | ±1.8 m | 86.0–89.6 m | ~0.04 m |
| **Medium-near** | ±5.4 m | 86.0–96.8 m | ~0.12 m |
| **Medium** | ±16.2 m | 86.0–118.4 m | ~0.36 m |
| **Outer** | ±48.6 m | 86.0–183.2 m | ~1.08 m |
| **Far-field** | ±81.0 m | 86.0–183.2 m | ~1.08 m |

The simulation is designed to run in **parallel using MPI**, with each mesh assigned to a dedicated MPI process (up to 153 processes).

### Boundary Conditions

| Boundary | Condition |
|---|---|
| XMIN, XMAX, YMIN, YMAX | `PERIODIC FLOW ONLY` |
| ZMIN (ground) | `GROUND` surface (roughness + temperature) |
| ZMAX (top) | `OPEN` |

---

## Output

The following quantities are saved as 3D slice files (`SLCF`) over the central domain (±48.6 m in XY, 86–183 m in Z):

- Temperature (with velocity vectors)
- Velocity (with velocity vectors)
- Pressure (with velocity vectors)
- CH₄ volume fraction

3D slice data is written every 1 second (`DT_SL3D = 1`), and XYZ geometry is exported for visualization (`WRITE_XYZ = T`).

---

## How to Run

### Prerequisites

- [FDS](https://github.com/firemodels/fds) (version ≥ 6.8 recommended)
- MPI runtime (e.g., OpenMPI or MPICH)

### Running

```bash
mpiexec -n 153 fds ch4_release.fds
```

Adjust `-n` to match the number of MPI processes available on your system. For testing with fewer cores, reduce the number of meshes in the input file accordingly.

### Visualization

Results can be visualized with [Smokeview (SMV)](https://pages.nist.gov/fds-smv/):

```bash
smokeview ch4_release
```

---

## File Structure

```
.
├── ch4_release.fds       # Main FDS input file
└── README.md             # This file
```

---

## References

- McGrattan, K. et al. *Fire Dynamics Simulator User's Guide*. NIST Special Publication 1019. National Institute of Standards and Technology, Gaithersburg, MD. [https://pages.nist.gov/fds-smv/](https://pages.nist.gov/fds-smv/)
