"""
fds_mesh_generator.py
=====================
Generates FDS &MESH configurations with nested, multi-resolution domains.

Can be used in two ways:

1. As a standalone script (CLI):
       python fds_mesh_generator.py --res 1.0 --steps 4 --z_min 247 --mpi 1 --layers 2

2. As an importable module from another program:
       from fds_mesh_generator import MeshConfig, run

       config = MeshConfig(res=0.5, steps=3, z_min=300, mpi=4, layers=2)
       run(config)

In both cases the output is written to 'mesh.txt'.
"""

import argparse
from dataclasses import dataclass, field
from typing import Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class MeshConfig:
    """
    All parameters needed to drive the mesh generator.

    Attributes:
        res     : Starting (finest) X/Y resolution in metres.
        steps   : Number of resolution steps (each step triples the cell size).
        z_min   : Minimum Z coordinate of the domain.
        mpi     : MPI division factor — meshes per MPI process.
        layers  : Number of constant-resolution boundary layers added after
                  the last resolution step.
        ijk     : Cell counts per mesh in (I, J, K).
        output  : Path of the output text file consumed by the FDS builder.
    """
    res: float = 1.0
    steps: int = 4
    z_min: int = 247
    mpi: int = 1
    layers: int = 2
    ijk: Tuple[int, int, int] = field(default_factory=lambda: (30, 30, 30))
    output: str = "mesh.txt"


# ---------------------------------------------------------------------------
# Generator class (unchanged logic, accepts MeshConfig)
# ---------------------------------------------------------------------------

class FDSMeshGenerator:
    """
    Generates FDS &MESH lines for nested multi-resolution domains.

    State is encapsulated in the instance so that mesh IDs increment
    monotonically across all calls within one run.
    """

    def __init__(self, config: MeshConfig):
        self.config = config
        self.current_mesh_id = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_mesh_line(self, fh, x_start, x_end, y_start, y_end, z_start, z_end):
        ijk = self.config.ijk
        mpi_process = self.current_mesh_id // self.config.mpi
        fh.write(
            f"&MESH ID = 'mesh{self.current_mesh_id}', "
            f"IJK = {ijk[0]}, {ijk[1]}, {ijk[2]}, "
            f"XB = {x_start:.2f}, {x_end:.2f}, {y_start:.2f}, {y_end:.2f}, "
            f"{z_start:.2f}, {z_end:.2f}, "
            f"MPI_PROCESS={mpi_process}, CHECK_MESH_ALIGNMENT=T/\n"
        )
        self.current_mesh_id += 1

    # ------------------------------------------------------------------
    # Core mesh writer
    # ------------------------------------------------------------------

    def generate_fds_meshes(self, fh, resolution, x_min, x_max, y_min, y_max, z_min, z_max):
        """Write &MESH lines that tile the given rectangular region."""
        ijk = self.config.ijk

        dx = resolution * ijk[0]
        dy = resolution * ijk[1]
        dz = resolution * ijk[2]

        num_x = int(round((x_max - x_min) / dx))
        num_y = int(round((y_max - y_min) / dy))
        num_z = int(round((z_max - z_min) / dz))

        x_coords = np.round(np.arange(x_min, x_max, dx), 2)
        y_coords = np.round(np.arange(y_min, y_max, dy), 2)
        z_coords = np.round(np.arange(z_min, z_max, dz), 2)

        for k in range(num_z):
            cz_min = z_coords[k]
            cz_max = round(cz_min + dz, 2)
            for j in range(num_y):
                y_start = y_coords[j]
                y_end = round(y_start + dy, 2)
                for i in range(num_x):
                    x_start = x_coords[i]
                    x_end = round(x_start + dx, 2)
                    self._write_mesh_line(fh, x_start, x_end, y_start, y_end, cz_min, cz_max)

            if k < num_z - 1:
                fh.write("\n")

    # ------------------------------------------------------------------
    # Multi-resolution domain builder
    # ------------------------------------------------------------------

    def generate_all_resolutions(self, fh, domain_factor=90):
        """
        Build nested mesh rings from finest to coarsest resolution.

        Returns a tuple of (final_resolution, final_domain_size, z_min, z_max)
        for use by subsequent boundary generators.
        """
        cfg = self.config
        current_res = cfg.res
        last_domain_size = 0.0
        last_z_size = 0.0
        z_max_curr = cfg.z_min  # will be updated each step

        for step in range(cfg.steps):
            domain_size = current_res * domain_factor
            dz = current_res * cfg.ijk[2]
            current_z_size = 3 * dz

            fh.write(f"# {current_res} m X/Y Resolution\n")

            if step == 0:
                self.generate_fds_meshes(
                    fh, current_res,
                    -domain_size / 2, domain_size / 2,
                    -domain_size / 2, domain_size / 2,
                    cfg.z_min, cfg.z_min + current_z_size,
                )
            else:
                xp0, xp1 = -last_domain_size / 2, last_domain_size / 2
                yp0, yp1 = -last_domain_size / 2, last_domain_size / 2
                xc0, xc1 = -domain_size / 2, domain_size / 2
                yc0, yc1 = -domain_size / 2, domain_size / 2
                zc0, zc1 = cfg.z_min, cfg.z_min + current_z_size
                zp1 = cfg.z_min + last_z_size

                fh.write("# Top Boundary\n")
                self.generate_fds_meshes(fh, current_res, xc0, xc1, yp1, yc1, zc0, zc1)

                fh.write("# Bottom Boundary\n")
                self.generate_fds_meshes(fh, current_res, xc0, xc1, yc0, yp0, zc0, zc1)

                fh.write("# Right Boundary\n")
                self.generate_fds_meshes(fh, current_res, xp1, xc1, yp0, yp1, zc0, zc1)

                fh.write("# Left Boundary\n")
                self.generate_fds_meshes(fh, current_res, xc0, xp0, yp0, yp1, zc0, zc1)

                fh.write("# Interior Z-domain expansion\n")
                self.generate_fds_meshes(fh, current_res, xp0, xp1, yp0, yp1, zp1, zc1)

            z_max_curr = cfg.z_min + current_z_size

            if step < cfg.steps - 1:
                fh.write("\n----------------------------------\n\n")
                last_domain_size = domain_size
                last_z_size = current_z_size
                current_res *= 3

        return current_res, domain_size, cfg.z_min, z_max_curr

    # ------------------------------------------------------------------
    # Constant-resolution outer boundary layers
    # ------------------------------------------------------------------

    def generate_constant_resolution_boundaries(self, fh, resolution, final_domain_size):
        """Append constant-resolution boundary rings around the outermost domain."""
        cfg = self.config
        ijk = cfg.ijk
        dx = resolution * ijk[0]
        dy = resolution * ijk[1]
        dz = resolution * ijk[2]

        fh.write("\n----------------------------------\n\n")
        fh.write(f"# {resolution} m Constant X/Y Resolution Boundaries\n")

        current_domain = final_domain_size

        for layer in range(cfg.layers):
            next_domain = current_domain + 2 * dx

            xp0, xp1 = -current_domain / 2, current_domain / 2
            yp0, yp1 = -current_domain / 2, current_domain / 2
            xc0, xc1 = -next_domain / 2, next_domain / 2
            yc0, yc1 = -next_domain / 2, next_domain / 2
            zc0 = cfg.z_min
            zc1 = cfg.z_min + 3 * dz

            fh.write(f"\n# Layer {layer + 1}: Positive Y Boundary, Resolution: {resolution}\n\n")
            self.generate_fds_meshes(fh, resolution, xc0, xc1, yp1, yc1, zc0, zc1)

            fh.write(f"\n# Layer {layer + 1}: Negative Y Boundary, Resolution: {resolution}\n\n")
            self.generate_fds_meshes(fh, resolution, xc0, xc1, yc0, yp0, zc0, zc1)

            fh.write(f"\n# Layer {layer + 1}: Positive X Boundary, Resolution: {resolution}\n\n")
            self.generate_fds_meshes(fh, resolution, xp1, xc1, yp0, yp1, zc0, zc1)

            fh.write(f"\n# Layer {layer + 1}: Negative X Boundary, Resolution: {resolution}\n\n")
            self.generate_fds_meshes(fh, resolution, xc0, xp0, yp0, yp1, zc0, zc1)

            current_domain = next_domain


# ---------------------------------------------------------------------------
# Public entry point — importable by other modules
# ---------------------------------------------------------------------------

def run(config: MeshConfig = None) -> str:
    """
    Execute the mesh generation with the given MeshConfig.

    If *config* is None a default MeshConfig() is used.
    Returns the path of the written output file.

    Example (from another module)::

        from fds_mesh_generator import MeshConfig, run

        config = MeshConfig(res=0.5, steps=3, z_min=300, mpi=4, layers=2)
        output_path = run(config)
        # output_path == "mesh.txt"  (or whatever config.output is set to)
    """
    if config is None:
        config = MeshConfig()

    generator = FDSMeshGenerator(config)

    with open(config.output, "w") as fh:
        final_res, final_domain, z_min, _ = generator.generate_all_resolutions(fh)
        generator.generate_constant_resolution_boundaries(fh, final_res, final_domain)

    print(f"Mesh written to '{config.output}' ({generator.current_mesh_id} meshes total).")
    return config.output


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args() -> MeshConfig:
    parser = argparse.ArgumentParser(
        description="Generate FDS mesh configuration (mesh.txt).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--res",    type=float, default=1.0,  help="Starting resolution in metres")
    parser.add_argument("--steps",  type=int,   default=4,    help="Number of resolution steps")
    parser.add_argument("--z_min",  type=int,   default=247,  help="Minimum Z coordinate")
    parser.add_argument("--mpi",    type=int,   default=1,    help="MPI division factor")
    parser.add_argument("--layers", type=int,   default=2,    help="Number of constant boundary layers")
    parser.add_argument("--output", type=str,   default="mesh.txt", help="Output file path")

    args = parser.parse_args()
    return MeshConfig(
        res=args.res,
        steps=args.steps,
        z_min=args.z_min,
        mpi=args.mpi,
        layers=args.layers,
        output=args.output,
    )


if __name__ == "__main__":
    run(_parse_args())
