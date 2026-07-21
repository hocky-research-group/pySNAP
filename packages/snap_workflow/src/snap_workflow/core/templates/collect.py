AUTO_SYNC = []

#Fill in this function to collect data from jobs in this stage. It will be called from 
#each job directory. It should take no params and should return a dict with name:data as 
#key:value pairs


def collect():
    #FIXME: Load data
    import numpy as np
    data1 = np.load("job_data1.npy") 
    data2 = np.load("job_data2.npy") 

    #FIXME: Make data dictionary
    data_dict = {"data1":data1,"data2":data2}
    return data_dict
