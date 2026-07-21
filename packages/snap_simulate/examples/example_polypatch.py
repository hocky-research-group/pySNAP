import os
from snap_workflow.core.params.system_params import System_Params
from snap_simulate.system import gen_mixture

def main():
    # Load parameters from the modular subdirectory
    param_path = os.path.join(os.path.dirname(__file__), "params_polypatch")
    params = System_Params(param_path)

    outfile = "example_polypatch.gsd"
    print(f"Generating polypatch system GSD file at {outfile}...")
    gen_mixture(params, outfile)
    print("System generation complete!")

    # Attempt to build and run the HOOMD simulation if HOOMD is installed
    try:
        import hoomd
        from snap_simulate.hoomd import build_simulation
        print("\nBuilding HOOMD simulation...")
        sim, hoomd_objs = build_simulation(params)
        # Build and run Langevin MD simulation directly
        print("Running Langevin MD simulation for 100,000 steps...")
        sim.run(100000)
        print("Simulation complete! Trajectory saved to example_polypatch_trajectory.gsd")
    except ImportError:
        print("\nNote: 'hoomd' is not installed in the current environment.")
        print("To run the molecular dynamics simulation, please install HOOMD-blue and run this script again.")

if __name__ == "__main__":
    main()
