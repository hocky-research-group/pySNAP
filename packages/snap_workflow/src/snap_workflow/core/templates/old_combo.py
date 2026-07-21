import snap_workflow

#---- General Info ----
#This script is run from its corresponding combo directory and has access to the 
#combo params via params.pkl, root/scripts/stage/ via scripts, and any dependencies
#via the dependency stage name

#---- Get Parameters ----
#Get all system params with combo vars already defined and stage set (if applicable)
#If update in params, uses that information to update the params. Useful if this 
#combo's params is directly dependent on a combo dependency output (like a json).
params = snap_workflow.load_params()
params.update() 

#---- Get Combo Vars ----
#Combo variables in a dict, they're already loaded into params though
combo_vars = snap_workflow.load_combo() 

#---- Context Manager ----
#If your combo isn't finished with 60 seconds left in the submission, then interrupt is sent by slurm and caught
#by the following context manager to shut down your combo and mark it as incomplete. The bulk of your code 
#should be run within the context manager (the following with statement).

#A function without arguments can be passed to help save the current iteration
def save_data():
    #Add code here if desired
    return

with snap_workflow.Combo_Manager(save_data) as combo_manager:
    #FIXME: Add code here 
