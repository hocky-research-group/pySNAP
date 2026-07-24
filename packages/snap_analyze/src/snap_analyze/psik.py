import numpy as np
import itertools
from .neighbor_list import NeighborList

class Psi_k():# {{{
    def __init__(self,k,box_length=None,r_nn=None,r_tol=None):# {{{
        self.k = k
        self.dim_flags = ~(box_length == 0)
        box_length = box_length[self.dim_flags]
        self.box_length = box_length
        self.half_box_length = box_length/2
        self.dim = np.count_nonzero(self.dim_flags)
        if r_nn is not None:
            self.r_cut = r_nn*(1+r_tol)
            self.nlist = NeighborList(self.r_cut,box_length,half=True)
        #}}}
    def _getWrappedDelta(self,pos1,pos2):# {{{
        delta = pos1-pos2
        signs = np.sign(delta)
        delta = np.abs(delta)
        wrap_flag = np.argwhere(delta > self.half_box_length).T
        delta[*wrap_flag] = self.box_length[wrap_flag[-1]] - delta[*wrap_flag]
        signs[*wrap_flag] *= -1
        return delta*signs
        # }}}
    def compute(self,pos,P1=None,P2=None):# {{{
        if len(pos.shape) == 2:
            num_particles = pos.shape[0]
            dims = pos.shape[1]
        else:
            raise Exception("Positions should be passed to the RDF as an Nxd array where N is the number of particles and d is the dimension")


        if P1 is None or P2 is None:
            pos = pos[:,self.dim_flags]
            P1,P2 = self.nlist(pos)
            delta = self._getWrappedDelta(pos[P1], pos[P2])
            dist = np.linalg.norm(delta,axis=-1)

            flag = dist<self.r_cut
            P1 = P1[flag]
            P2 = P2[flag]
            delta = delta[flag]
        else:
            delta = self._getWrappedDelta(pos[P1], pos[P2])

        #import matplotlib.pyplot as plt
        #for i in range(num_particles):
            #flag = np.logical_or(P1 == i,P2==i)
            #ids = np.concatenate([P1[flag],P2[flag]])
            #print(ids)
            #plt.plot(*pos.T,'ko',markersize=1)
            #plt.plot(*pos[ids].T,'ro')
            #plt.plot(*pos[i],'co')
            #plt.show()

        theta = np.arctan2(delta[:,0],delta[:,1])
        exp = np.exp(1j*(self.k*theta))

        Psi1 = np.bincount(P1,exp.real,minlength=num_particles)
        Psi1 = Psi1 + 1j*np.bincount(P1,exp.imag,minlength=num_particles)

        Psi2 = np.bincount(P2,exp.real,minlength=num_particles)
        Psi2 = Psi2 + 1j*np.bincount(P2,exp.imag,minlength=num_particles)

        n = np.bincount(P1,minlength=num_particles) + np.bincount(P2,minlength=num_particles)

        Psi = np.abs(Psi1 + Psi2)/n
        Psi[n==0] = 0
        return Psi
        #}}}
# }}}
