def minimize_autocorrelation(sim,max_steps,sample_rate,sample_function,check_rate,check_function):# {{{
    minimized = False
    samples = []
    timesteps = []
    steps_since_check = 0
    total_steps = 0
    while not minimized and total_steps < max_steps:
        sim.run(sample_rate)

        snap = sim.state.get_snapshot()
        timestep = sim.timestep
        sample = sample_function(timestep,snap)
        samples.append(sample)
        timesteps.append(timestep)

        steps_since_check += sample_rate
        total_steps += sample_rate

        if steps_since_check >= check_rate:
            steps_since_check = 0
            minimized,auto = check_function(timesteps,samples)

    if not minimized:
        import warnings
        warnings.warn(f"Unable to minimize autocorrelation within {max_steps} timesteps")
    else:
        print()
        print(f"Finished minimizing autocorrelation function in {total_steps} timesteps")
        print()

    res = {"minimized":minimized,
           "auto":auto,
           "steps_ran":total_steps}

    return res 
# }}}
def min_auto_FSKT(sim,ptype,num_avg=10,min_value=0.01):# {{{
    import numpy as np
    from nyut_analyze import dynamics
    dt = sim.operations.integrator.dt
    box = sim.state.box.L
    dyn = dynamics(box,kmag=1.1)

    def sample_function(timestep,frame):
        pos = frame.particles.position
        image = frame.particles.image

        particle_types = frame.particles.typeid
        flags = particle_types == ptype

        pos = pos[flags]
        image = image[flags]

        dyn.append_timestep(timestep, pos, image)
        return None

    def check_function(timesteps,samples):
        dyn.compute()
        dt,Fskt = dyn.calc_Fskt()
        if len(Fskt) < num_avg:
            return False,Fskt
        auto = np.mean(Fskt[-num_avg:])

        if auto < min_value:
            return True,Fskt
        return False,Fskt

    return sample_function,check_function
# }}}
def min_auto_PE(logger,num_avg=10,min_value=0.01):# {{{
    import numpy as np

    def sample_function(timestep,frame):
        PE = logger.log()['md']['compute']["ThermodynamicQuantities"]["potential_energy"][0]
        return PE

    def check_function(timesteps,samples):

        avg = samples - np.mean(samples)
        var = np.var(samples)
        ft_signal = np.fft.rfft(avg)
        convolution = ft_signal * np.conjugate(ft_signal)
        auto = np.fft.irfft(convolution)/(len(samples)*var)
        last_auto = np.mean(auto[-num_avg:])

        if len(samples) < num_avg:
            return False,auto

        if auto < min_value:
            return True,auto
        return False,auto

    return sample_function,check_function
# }}}
