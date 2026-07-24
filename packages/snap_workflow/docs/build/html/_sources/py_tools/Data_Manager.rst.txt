DataManager
===========

Implemented internally with numpy arrays, the :py:class:`DataManager` is the data structure that stores all collected data by :program:`workflow collect`.
After running :program:`workflow collect` a pickled :py:class:`DataManager` can be found in each stage's :file:`collect` directory as :file:`*stage_name*.pkl`.
:py:class:`DataManager` (legacy alias: ``Data_Manager``) objects provide useful utility for filtering and sorting collected data by job variables.
See the below examples and documentation for more info on this utility.

.. code:: python
    
    from snap_workflow import DataManager

    # Load in DataManager with:
    #    Job variables: N(int), eta(float), gamma(float)
    #    Collected data: t, bonds (both numpy arrays)
    dm = DataManager("path/to/data_manager.pkl")


    #Filter by variable comparison
    etas = dm["eta"] #All eta instances (numpy array)
    dm_e = dm[etas > 0.05]


    #Filter by multiple comparisons
    gammas = dm["gammas"]
    dm_eg = dm_e[gammas > 1.5]
        #Or equivalently
    dm_eg = dm[etas > 0.05, gammas > 1.5]


    #Split Data_Manager via unique instances of a variable 
    Ns = dm["N"]
    unique_Ns = dm.unique("N") #Unique instances (numpy array)
    for N in unique_Ns:
        dm_N = dm[Ns == N]
        ...

    #Or equivalently
    Ns,dm_Ns = dm.split("N")
    for N,dm_N in zip(matrices,dm_Ns):
        ...


    #Iterate through each instance
    for data in dm:
        eta = data["eta"] #float
        gamma = data["gamma"] #float
        N = data["N"] #int

        t = data["t"] #numpy array
        bonds = data["bonds"] #numpy array

        ...
    

.. autoclass:: snap_workflow::Data_Manager

    .. automethod:: unique
    .. automethod:: split

