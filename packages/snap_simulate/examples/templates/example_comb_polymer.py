import os
from snap_workflow.core.params.system_params import System_Params
from snap_simulate.system import gen_mixture

def main():
    # Load parameters from the modular subdirectory
    param_path = os.path.join(os.path.dirname(__file__), "params_comb_polymer")
    params = System_Params(param_path)

    outfile = "example_comb_polymer.gsd"
    print(f"Generating comb polymer GSD file at {outfile}...")
    gen_mixture(params, outfile)
    print("System generation complete!")

if __name__ == "__main__":
    main()
