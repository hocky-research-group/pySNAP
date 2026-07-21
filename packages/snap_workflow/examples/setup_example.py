import os
import sys
import shutil

# Make sure we can import the local snap_workflow package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import snap_workflow.core as wf

def main():
    # Define and clean the target directory
    target_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "example_A"))
    if os.path.exists(target_dir):
        print(f"Cleaning existing directory: {target_dir}")
        shutil.rmtree(target_dir)
        
    os.makedirs(target_dir, exist_ok=True)
    os.chdir(target_dir)
    print(f"Initializing workflow inside: {target_dir}")

    # Initialize the workflow. We use a dummy directory for python environment
    dummy_env = os.path.join(target_dir, ".dummy_env")
    os.makedirs(dummy_env, exist_ok=True)
    wf.initialize(dummy_env)

    # 1. Add variables
    print("Registering variables...")
    wf.add_variable("mesh_size", ["int"])
    wf.add_variable("reynolds_number", ["float"])
    wf.add_variable("time_step", ["float"])

    # 2. Add 4 linearly dependent stages
    # - domain_discretizer (Pre-processing: generates geometry grid)
    # - navier_stokes_solver (Solver: simulates flow dynamics)
    # - vortex_detector (Post-processing: filters vortex cores)
    # - render_engine (Visualization: renders outputs)
    print("Creating stages...")
    wf.add_stage(
        stage_name="domain_discretizer",
        sbatch_details=None,
        stage_variables=["mesh_size"],
        stage_dependencies=[]
    )
    wf.add_stage(
        stage_name="navier_stokes_solver",
        sbatch_details=None,
        stage_variables=["mesh_size", "reynolds_number", "time_step"],
        stage_dependencies=["domain_discretizer"]
    )
    wf.add_stage(
        stage_name="vortex_detector",
        sbatch_details=None,
        stage_variables=["reynolds_number"],
        stage_dependencies=["navier_stokes_solver"]
    )
    wf.add_stage(
        stage_name="render_engine",
        sbatch_details=None,
        stage_variables=["mesh_size"],
        stage_dependencies=["vortex_detector"]
    )

    # 3. Add two different matrix sweeps
    print("Setting up sweeps...")
    # Sweep A: Laminar flow configurations (lower Reynolds numbers)
    wf.add_sweep(
        sweep_name="laminar_flow_sweep",
        include_stages=["domain_discretizer", "navier_stokes_solver", "vortex_detector", "render_engine"],
        variable_values={
            "mesh_size": [64, 128],
            "reynolds_number": [10.0, 100.0],
            "time_step": [0.01]
        }
    )

    # Sweep B: Turbulent flow configurations (higher Reynolds numbers, finer meshes)
    wf.add_sweep(
        sweep_name="turbulent_flow_sweep",
        include_stages=["domain_discretizer", "navier_stokes_solver", "vortex_detector", "render_engine"],
        variable_values={
            "mesh_size": [256],
            "reynolds_number": [2000.0, 5000.0],
            "time_step": [0.001, 0.005]
        }
    )

    print("\nWorkflow setup successfully completed in stage-oriented layout!")
    print(f"Root: {target_dir}")

if __name__ == "__main__":
    main()
