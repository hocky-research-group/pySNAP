import sys
import numpy as np
import scipy.fft as fft

class Print_Manager():# {{{
    def __init__(self,verbose):
        self.verbose = verbose
    def __call__(self,*args,**kwargs):
        if not self.verbose:
            return
        print(*args,**kwargs)
        return# }}}
class Old_Static_Structure_Factor():# {{{
    def __init__(self, cell_size, box_length, isotropic = False,verbose = False):# {{{
        self.print = Print_Manager(verbose)
        print = self.print
        if len(box_length) == 3:
            self.box_length = box_length
        else:
            self.box_length = box_length[:3]
        self.half_box_length = self.box_length/2
        self.isotropic = isotropic
        self.cell_size = cell_size
        self.average = 0
        self.count = 0
        if len(np.unique(self.box_length)) != 1:
            sys.tracebacklimit = 0
            raise Exception("Box is not a cube")

        if isotropic:
            self._setup_iso()
        else:
            self._setup_noniso()# }}}
    def append(self,pos):# {{{
        if self.isotropic:
            self._compute_iso(pos)
        else:
            self._compute_noniso(pos)
        return# }}}
    def get_3D_qS(self,):# {{{
        if self.isotropic:
            sys.tracebacklimit = 0
            raise Exception("3D values not calculated if isotropic flag set to true")
        return self.q3,self.s3/self.s3_count# }}}
    def get_1D_qS(self):# {{{
        average = self.s3/self.s3_count
        s1 = np.bincount(self.q1_idx,average)
        s1 = s1/self.qcount
        return self.qmids,s1[1:]
    # }}}

    def _setup_iso(self):# {{{
        self.s1_all = []
        self.iso_factor = 10
        cell_size = self.cell_size
        num_boxes = int(np.linalg.norm(self.box_length)/cell_size)
        cell_size = np.linalg.norm(self.box_length)/num_boxes
        self.sample_cell_size = cell_size/self.iso_factor

        #Assumes box is cubic
        self.num_sample_boxes = int(num_boxes * self.iso_factor)
        self.sample_cell_size = np.linalg.norm(self.box_length)/self.num_sample_boxes

        self.q1_idx = np.array([[i]*self.iso_factor] for i in range(num_boxes))
        self.q1_idx = self.q1_idx[flaten]

        rs = np.linspace(0,np.linalg.norm(self.box_length),self.num_sample_boxes)
        rmid = np.average(rs.reshape(int(len(rs)/self.iso_factor),self.iso_factor),axis = -1)


        box_length = self.box_length[0]
        self.box_length = box_length
        self.max_flag = rmid < self.box_length

        min_q = 2*np.pi/box_length
        self.max_q = min_q*int(num_boxes)
        #q1 = min_q*(np.arange(num_boxes) - int(num_boxes/2))
        q1 = min_q*np.arange(num_boxes)

        self.nonzero = q1 != 0
        #self.q1 = q1[self.nonzero]
        self.qmids = q1[self.max_flag]
        #self.qmids = (q1[1:] + q1[:-1])/2
# }}}
    def _compute_iso(self,pos):# {{{
        #Calc dist from neighbor list
        counts = self._gen_counts_iso(pos)

        #s1 = fft.fftshift(fft.dct(counts))
        s1 = fft.dct(counts)
        s1 = np.abs(s1)**2/pos.shape[0]
        #s1 = s1[self.nonzero]
        #s1[self.nonzero] = 0
        s1 = np.average(s1.reshape(int(len(s1)/self.iso_factor),self.iso_factor),axis = -1)
        s1 = s1[self.max_flag]

        self.s1_all.append(s1)# }}}
    def _gen_counts_iso(self,particles):#{{{
        box_length = self.box_length
        num_boxes = self.num_sample_boxes
        cell_size = self.sample_cell_size

        if np.any(particles < 0):
            particles += box_length/2

        particles = np.linalg.norm(particles,axis = -1)
        indices = (particles/cell_size).astype(int)
        count = np.zeros(num_boxes)

        for i,idx in enumerate(indices):
            count[idx] += 1
        #count /= 4*np.pi*self.rmid**2*self.cell_size
        return count
#}}}

    def _setup_noniso(self):# {{{
        self.s3_all = []

        box_length = self.box_length
        num_boxes = (box_length/self.cell_size).astype(int)
        self.num_boxes = num_boxes
        self.cell_size = box_length/self.num_boxes

        min_q = 2*np.pi / box_length
        q3 = min_q*np.array([np.arange(num_boxes[i]) 
                                    - int(num_boxes[i]/2) 
                                       for i in range(3)]).T

        q3 = np.array(np.meshgrid(*q3.T)).T
        q1 = np.linalg.norm(q3,axis = 3)
        s3 = np.zeros_like(q1)
        s3 = s3.flatten()
        q1 = q1.flatten()
        
        #The smallest real box length will set the max qsphere radius
        num = np.min((num_boxes-(num_boxes/2).astype(int)))
        q1_sphere = np.min(num*min_q)
        sphere_flag = q1<q1_sphere
        q1 = q1[sphere_flag]
        s3 = s3[sphere_flag]


        #Make q1 averaging bins
        spacing = np.mean(min_q)
        spacing = q1_sphere/num
        q1_idx = (q1/spacing).astype(int)
        qcount = np.bincount(q1_idx)
        qspacing = np.linspace(0,q1_sphere,num+1)
        qmids = ((qspacing[:-1] + qspacing[1:])/2)

        #self.non_zero = non_zero
        self.sphere_flag = sphere_flag
        self.qcount = qcount
        self.qmids = qmids[1:]
        self.nonzero = q1 != 0
        self.q1_idx = q1_idx[self.nonzero]
        self.q3 = q1[self.nonzero]
        self.s3 = s3[self.nonzero]
        self.s3_count = 0
# }}}
    def _compute_noniso(self,pos):# {{{
        #Calc dist from neighbor list
        counts = self._gen_counts_noniso(pos)

        S3 = fft.fftshift(fft.fftn(counts))
        S3 = np.abs(S3)**2/np.sum(counts)

        s3 = S3.flatten()
        s3 = s3[self.sphere_flag]
        s3 = s3[self.nonzero]
        self.s3 += s3
        self.s3_count += 1
        #self.s3_all.append(s3[self.nonzero])
        # }}}
    def _gen_counts_noniso(self,particles):#{{{
        box_length = self.box_length
        num_boxes = self.num_boxes
        cell_size = self.cell_size

        if np.any(particles < 0):
            particles += box_length/2

        indices = (particles/cell_size).astype(int)
        count = np.zeros(num_boxes)

        for i,idx in enumerate(indices):
            index = tuple(idx.tolist())
            count[index] += 1
        return count
#}}}

    def __call__(self,pos):# {{{
        self.compute(pos)# }}}
# }}}
class Static_Structure_Factor:
    """
    Computes the static structure factor :math:`S(\\vec{k})` and 1D spherically averaged :math:`S(k)` via Fast Fourier Transforms (FFT).

    Parameters
    ----------
    cell_size : float
        Target grid cell size for spatial grid binning before FFT.
    box_length : array_like
        Length of the simulation box in each dimension.
    verbose : bool, optional
        If True, prints diagnostic output during calculations. Default is False.
    """

    def __init__(self, cell_size, box_length, verbose=False):
        self.print = Print_Manager(verbose)
        print = self.print

        dim_flag = box_length != 0
        dims = np.count_nonzero(dim_flag)
        box = box_length[dim_flag]

        num_boxes = np.ceil(box / cell_size).astype(int)
        cell_size = box / num_boxes

        self.num_boxes = num_boxes
        self.cell_size = cell_size
        self.box = box
        self.dim_flag = dim_flag

        self.k = (
            np.array(np.meshgrid(*[fft.fftshift(fft.fftfreq(n, d=1 / n)) for n in num_boxes])).T
            * (2 * np.pi / box)
        )
        self.S = None
        self.num_frames = 0

    def append(self, positions):
        """
        Accumulate a frame of particle positions for structure factor averaging.

        Parameters
        ----------
        positions : ndarray
            Particle position array of shape (N, d).
        """
        num_boxes = self.num_boxes
        cell_size = self.cell_size
        dim_flag = self.dim_flag
        box = self.box

        positions = positions[:, dim_flag]
        if np.any(positions < 0):
            positions = np.copy(positions)
            positions += box / 2

        idx = (positions / cell_size).astype(int)
        count = np.zeros(num_boxes)
        count[*idx.T] += 1

        S = fft.fftshift(fft.fftn(count))
        S = np.abs(S) ** 2 / positions.shape[0]
        if self.S is None:
            self.S = S
        else:
            self.S += S
        self.num_frames += 1

    def get_Sk(self):
        """
        Get full reciprocal space wavevectors and frame-averaged structure factor array :math:`S(\\vec{k})`.

        Returns
        -------
        k : ndarray
            Reciprocal wavevectors grid matching structure factor grid dimensions.
        S : ndarray
            Frame-averaged structure factor :math:`S(\\vec{k})`.
        """
        return self.k, self.S / self.num_frames

    def get_1D_Sk(self, **kwargs):
        """
        Spherically average :math:`S(\\vec{k})` into 1D scalar wavevector magnitude dependence :math:`S(k)`.

        Parameters
        ----------
        **kwargs
            Additional keyword arguments passed to `np.histogram`.

        Returns
        -------
        k : ndarray
            1D wavevector magnitudes :math:`k`.
        Sk : ndarray
            Spherically averaged structure factor :math:`S(k)`.
        """
        S = self.S / self.num_frames

        k_mag = np.linalg.norm(self.k, axis=-1)
        k_sphere = np.min(self.num_boxes * (2 * np.pi / self.box))
        k_flag = k_mag < k_sphere

        k_mag = k_mag[k_flag]
        S = S[k_flag]
        kmin = int(np.floor(np.log10(np.min(k_mag[k_mag != 0]))))
        kmax = int(np.ceil(np.log10(np.max(k_mag))))
        bins = np.logspace(kmin, kmax, 100 * (kmax - kmin))
        N, _ = np.histogram(k_mag, bins=bins, **kwargs)
        S, k = np.histogram(k_mag, weights=S, bins=bins, **kwargs)
        k = (k[:-1] + k[1:]) / 2
        flag = (k != 0) & (S != 0)
        return k[flag], S[flag] / N[flag]

    def __call__(self, positions=None):
        """
        Accumulate positions if provided, or compute structure factor.
        """
        if positions is None:
            self.append(positions)
        else:
            self.get_Sk()

