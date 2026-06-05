"""
build_fds_inputFile.py
============
Parses simulation parameters, runs the FDS mesh generator as a module,
then assembles the full 'inputfile.fds' from mesh.txt plus all other
simulation sections.

Usage:
    python build_fds.py
"""

import sys
import os
import textwrap

# ---------------------------------------------------------------------------
# 1.  Simulation parameters  (edit these)
# ---------------------------------------------------------------------------

# Header
CHID               = "coalmine_shaft"
TITLE              = "FDS Simulation of Coal mine Ventilation shaft at High resolution"
LAT                = 49.97530787582345
LON                = 18.735595777923024 
NORTH_BEARING      = 0
LEVEL_SET_MODE     = 3
THICKEN_OBSTRUCTIONS = "T"

# Domain / time
START_DATE         = "2024-06-01"
START_TIME         = "12:00:00"
SIM_DURATION_S     = 3600

# Mesh resolution
HIGHEST_RESOLUTION = 1      # starting (finest) resolution in metres
STEPS              = 4      # number of 3× resolution jumps
LAYERS             = 2      # constant-resolution outer boundary rings
Z_MIN              = 247    # lowest Z coordinate in the domain
MPI                = 1      # meshes per MPI process

# Terrain Topography
TERRAIN_FILE = "terrain.txt"
LOCAL_TIF    = None   # or LOCAL_TIF = "/absolute/path/to/high_resolution_terrain.tif", if any high resolution terrain information available
                      
# Gases: Mass Fractions (if any) and mass
PURE_METHANE       = True

# CH4 Source details
CH4_FLUX           = 20.23  # kg/m^2/s
Z_SOURCE           = 28 # meters| Height of source above Z_MIN

# Boundary conditions

GROUND_SURF      = "GROUND"
LATERAL_SURF_BC  = "PERIODIC FLOW ONLY"
TOP_SURF_BC      = "OPEN"

# Quantities to save (comment out any you don't want)
SLCF_QUANTITIES = [
    {"QUANTITY": "TEMPERATURE",     "VECTOR": ".TRUE."},
    {"QUANTITY": "U-VELOCITY"},
    {"QUANTITY": "V-VELOCITY"},
    {"QUANTITY": "W-VELOCITY"},
    {"QUANTITY": "PRESSURE",        "VECTOR": ".TRUE."},
    {"QUANTITY": "VOLUME FRACTION", "SPEC_ID": "'METHANE'"},
]

# ---------------------------------------------------------------------------
# 2a.  Run the mesh generator (writes mesh.txt)
# ---------------------------------------------------------------------------

# Make sure fds_mesh_generator.py is importable from the same directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.mesh_generation.fds_mesh_generator import MeshConfig, run as generate_mesh

MESH_FILE = "mesh.txt"

mesh_cfg = MeshConfig(
    res    = HIGHEST_RESOLUTION,
    steps  = STEPS,
    z_min  = Z_MIN,
    mpi    = MPI,
    layers = LAYERS,
    output = MESH_FILE,
)

print("Generating mesh …")
mesh_result = generate_mesh(mesh_cfg)

DOMAIN_X_MIN = mesh_result["x_min"]
DOMAIN_X_MAX = mesh_result["x_max"]
DOMAIN_Y_MIN = mesh_result["y_min"]
DOMAIN_Y_MAX = mesh_result["y_max"]
DOMAIN_Z_MIN = mesh_result["z_min"]
DOMAIN_Z_MAX = mesh_result["z_max"]

# ---------------------------------------------------------------------------
# 2b.  Download ERA5 data (writes NetCDF + FDS RAMP .txt)
# ---------------------------------------------------------------------------
from modules.meteorological_parameters.era5_downloader import run as download_era5

print("Downloading ERA5 data …")
era5_results = download_era5(
    lat     = LAT,
    lon     = LON,
    date    = START_DATE,
    hour    = int(START_TIME.split(":")[0]),   # extracts 12 from "12:00:00"
    z_min = Z_MIN,
)

RAMP_FILE    = era5_results["ramp_txt"]      # path to the generated RAMP .txt
T2M          = era5_results["t2m"]           # → TMPA in &MISC
SKIN_TEMP    = era5_results["skin_temp"]     # → TMP_FRONT in &SURF for ground
SURFACE_PRES = era5_results["surface_pres"]  # → P_INF in &MISC

# ---------------------------------------------------------------------------
# 2c.  Generate terrain (reads mesh.txt, writes terrain.txt)
# ---------------------------------------------------------------------------
from modules.terrain.elevation_to_fds import get_terrain, parse_mesh_file

print("Generating terrain …")
domain_size, terrain_resolutions = parse_mesh_file(MESH_FILE)
get_terrain(
    lat         = LAT,
    lon         = LON,
    size_m      = domain_size,
    output_file = TERRAIN_FILE,
    resolutions = terrain_resolutions,
    local_tif   = LOCAL_TIF,

)

# ---------------------------------------------------------------------------
# 3.  Build inputfile.fds
# ---------------------------------------------------------------------------

OUTPUT_FDS = "inputfile.fds"

# ---- helpers ---------------------------------------------------------------

def fds_date_time(date_str: str, time_str: str):
    """Return (YYYY, MM, DD, HH, MM, SS) from 'YYYY-MM-DD' and 'HH:MM:SS'."""
    y, mo, d  = date_str.split("-")
    h, mi, s  = time_str.split(":")
    return int(y), int(mo), int(d), int(h), int(mi), int(s)

year, month, day, hour, minute, second = fds_date_time(START_DATE, START_TIME)

# ---- section builders ------------------------------------------------------

def section_head() -> str:
    return textwrap.dedent(f"""\
        ! ============================================================
        !  FDS input file – auto-generated by build_fds_inputFile.py
        ! ============================================================
        &HEAD CHID='{CHID}',
              TITLE='{TITLE}' /

    """)


def section_time() -> str:
    return textwrap.dedent(f"""\
        ! ------------------------------------------------------------
        !  Time
        ! ------------------------------------------------------------
        &TIME T_END={SIM_DURATION_S}.0, /

    """)


def section_misc() -> str:
    return textwrap.dedent(f"""\
        ! ------------------------------------------------------------
        !  Miscellaneous setup
        ! ------------------------------------------------------------
        &MISC ORIGIN_LAT={LAT},
              ORIGIN_LON={LON},
              LEVEL_SET_MODE={LEVEL_SET_MODE},
              THICKEN_OBSTRUCTIONS=.{THICKEN_OBSTRUCTIONS}.,
              NORTH_BEARING={NORTH_BEARING:.1f},
              TMPA={T2M:.2f},
              P_INF={SURFACE_PRES:.2f} /

    """)


def section_wind() -> str:
    """Read &WIND and &RAMP lines from the ERA5-generated file."""
    try:
        with open(RAMP_FILE, "r") as fh:
            content = fh.read()
        return (
            "! ------------------------------------------------------------\n"
            "!  Wind / atmospheric boundary conditions  (from ERA5)\n"
            "! ------------------------------------------------------------\n"
            + content
            + "\n"
        )
    except FileNotFoundError:
        return (
            "! WARNING: ERA5 RAMP file not found — using placeholder wind\n"
            "&WIND SPEED=5.0, DIRECTION=270.0 /\n\n"
        )

def section_ground_surf() -> str:
    return textwrap.dedent(f"""\
        ! ------------------------------------------------------------
        !  Ground surface
        ! ------------------------------------------------------------
        &SURF ID={GROUND_SURF},
              ROUGHNESS=0.978,
              COLOR='BROWN',
              TMP_FRONT={SKIN_TEMP:.2f},
              THICKNESS=0.1 /

    """)

def section_gas_species() -> str:
    if PURE_METHANE:
        return textwrap.dedent(f"""\
        ! ------------------------------------------------------------
        !  GAS SPECIES
        ! ------------------------------------------------------------
        &SPEC ID='METHANE'/

        &SPEC ID='AIR', BACKGROUND=T/

        """)
    
    else:   # An example: 0.12 % Methane at 98 % RELATIVE HUMIDITY
        return textwrap.dedent(f"""\
        ! ------------------------------------------------------------
        !  GAS SPECIES
        ! ------------------------------------------------------------
        &SPEC ID='METHANE'/
        
        &SPEC ID='AIR', BACKGROUND=T/

        
        &SPEC ID='METHANE AIR MIXTURE', SPEC_ID(1)='AIR',     MASS_FRACTION(1)=0.98087962,
                                        SPEC_ID(2)='METHANE', MASS_FRACTION(2)=0.00065249,
				        SPEC_ID(3)='WATER VAPOR', MASS_FRACTION(3)=0.01846789/
        
        """)

def section_source_details() -> str:
    return textwrap.dedent(f"""\
        ! ------------------------------------------------------------
        !  CH4 SOURCE
        ! ------------------------------------------------------------
        &SURF ID='METHANE BLOWER', MASS_FLUX(1)={CH4_FLUX}, SPEC_ID(1)='METHANE AIR MIXTURE', COLOR='RED'/

        &OBST XB= -3.0, 1.0, 1.5, 4.98,  {Z_MIN:.2f}, {(Z_MIN+Z_SOURCE):.2f} /
        &VENT XB= -3.0, 1.0, 1.5, 4.98,  {(Z_MIN+Z_SOURCE):.2f}, {(Z_MIN+Z_SOURCE):.2f}, SURF_ID='METHANE BLOWER' /

        """)

def section_boundary_conditions() -> str:
    return textwrap.dedent(f"""\
        ! ------------------------------------------------------------
        !  BOUNDARY CONDITIONS
        ! ------------------------------------------------------------
        &VENT DB='XMIN', SURF_ID='{LATERAL_SURF_BC}' /
        &VENT DB='XMAX', SURF_ID='{LATERAL_SURF_BC}' /
        &VENT DB='YMIN', SURF_ID='{LATERAL_SURF_BC}' /
        &VENT DB='YMAX', SURF_ID='{LATERAL_SURF_BC}' /
        &VENT DB='ZMIN', SURF_ID='{GROUND_SURF}' /
        &VENT DB='ZMAX', SURF_ID='{TOP_SURF_BC}' /
    
        """)

def section_slcf() -> str:
    xb = (f"{DOMAIN_X_MIN:.2f}, {DOMAIN_X_MAX:.2f}, "
          f"{DOMAIN_Y_MIN:.2f}, {DOMAIN_Y_MAX:.2f}, "
          f"{DOMAIN_Z_MIN:.2f}, {DOMAIN_Z_MAX:.2f}")
    lines = [
        "! ------------------------------------------------------------",
        "!  Slice files",
        "! ------------------------------------------------------------",
    ]
    for q in SLCF_QUANTITIES:
        extras = "".join(f", {k}={v}" for k, v in q.items() if k != "QUANTITY")
        lines.append(f"&SLCF XB={xb}, QUANTITY='{q['QUANTITY']}'{extras} /")
    return "\n".join(lines) + "\n\n"


def section_terrain() -> str:
    try:
        with open(TERRAIN_FILE, "r") as fh:
            content = fh.read()
        return (
            "! ------------------------------------------------------------\n"
            "!  Terrain obstructions  (generated by elevation_to_fds.py)\n"
            "! ------------------------------------------------------------\n"
            + content
            + "\n"
        )
    except FileNotFoundError:
        return "! WARNING: terrain file not found — skipping terrain obstructions\n\n"

def section_dump() -> str:
    return textwrap.dedent(f"""\
        ! ------------------------------------------------------------
        !  Output controls
        ! ------------------------------------------------------------
        &DUMP DT_SL3D=10.0,
              DT_DEVC=10.0
              WRITE_XYZ=T /

    """)


def section_tail() -> str:
    return textwrap.dedent("""\
        ! ------------------------------------------------------------
        !  End of input file
        ! ------------------------------------------------------------
        &TAIL /
    """)


# ---- read mesh.txt ---------------------------------------------------------

with open(MESH_FILE, "r") as fh:
    mesh_block = fh.read()

mesh_section = (
    "! ------------------------------------------------------------\n"
    "!  Mesh definitions  (generated by fds_mesh_generator.py)\n"
    "! ------------------------------------------------------------\n"
    + mesh_block
    + "\n"
)

# ---- assemble and write ----------------------------------------------------

fds_content = "".join([
    section_head(),
    section_misc(),
    mesh_section,
    section_time(),
    section_wind(),
    section_ground_surf(),
    section_gas_species(),
    section_source_details(),
    section_boundary_conditions(),
    section_slcf(),
    section_terrain(), 
    section_dump(),
    section_tail(),
])

with open(OUTPUT_FDS, "w") as fh:
    fh.write(fds_content)

print(f"FDS input file written to '{OUTPUT_FDS}'.")
