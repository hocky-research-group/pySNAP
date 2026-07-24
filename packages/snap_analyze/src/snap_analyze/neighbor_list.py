import numpy as np
import itertools
class NeighborList():# {{{
    def __init__(self,neighbor_cutoff,box_length,half=True):#{{{
        if not np.iterable(box_length):
            raise Exception("box_length must be a 1D array of length d (number of dimensions)")
        self.dim_flags = ~(box_length == 0)
        self.dim = np.count_nonzero(self.dim_flags)
        if np.any(self.dim_flags):
            box_length = box_length[self.dim_flags]
        num_boxes = (box_length/neighbor_cutoff).astype(int)
        if np.any(num_boxes < 3):
            raise Exception(f"Neighbor cutoff yields less than three boxes")
        self.cutoff = box_length/num_boxes
        self.num_boxes = num_boxes
        self.box_length = box_length
        self.half = half
        #}}}
    def __call__(self,pos):# {{{
        return self.compute(pos)
    # }}}
    def compute(self,pos):# {{{
        if np.any(pos < 0):
            pos += self.box_length/2
        if len(pos.shape) == 2:
            num_particles = pos.shape[0]
            dims = pos.shape[1]
            pos = pos[:,self.dim_flags]
        else:
            raise Exception("Positions should be passed into the neighbor list as an Nxd array where N is the number of particles and d is the dimension")

        indices = (pos/self.cutoff).astype(int)

        boxes = {}
        count = np.zeros(self.num_boxes)
        

        for i,idx in enumerate(indices):
            index = tuple(idx.tolist())
            if index not in boxes:
                boxes[index] = list()
            boxes[index].append(int(i))
            count[index] += 1

        num_boxes = self.num_boxes
        P1,P2 = [],[]
        offset = np.array([np.arange(-1,2) for i in range(dims)]).T
        for p1,idx in enumerate(indices):
            offsets = (idx+offset)%num_boxes
            for off in itertools.product(*offsets.T):
                if count[off] == 0:
                    continue
                p2s = boxes[off]
                P1 += [p1]*len(p2s)
                P2 += (p2s)
        P1 = np.array(P1)
        P2 = np.array(P2)


        if self.half:
            flags = P1 < P2
        else:
            flags = P1 != P2

        P1 = P1[flags]
        P2 = P2[flags]

        return P1,P2
        #}}}
#}}}
class MultiNeighborList():# {{{
    def __init__(self,neighbor_cutoff,box_length):#{{{
        if not np.iterable(box_length):
            raise Exception("box_length must be a 1D array of length d (number of dimensions)")
        self.dim_flags = ~(box_length == 0)
        self.dim = np.count_nonzero(self.dim_flags)
        if np.any(self.dim_flags):
            box_length = box_length[self.dim_flags]
        num_boxes = (box_length/neighbor_cutoff).astype(int)
        if np.any(num_boxes < 3):
            raise Exception(f"Neighbor cutoff yields less than three boxes")
        self.cutoff = box_length/num_boxes
        self.num_boxes = num_boxes
        self.box = box_length
        #}}}
    def __call__(self,pos1,pos2):# {{{
        return self._compute(pos1,pos2)
    # }}}
    def _compute(self,pos1,pos2):# {{{
        box_length = self.box
        cutoff = self.cutoff
        numBoxes = self.num_boxes

        if np.any(pos1 < 0) or np.any(pos2 < 0):
            pos1 = np.copy(pos1)
            pos1 += box_length/2

            pos2 = np.copy(pos2)
            pos2 += box_length/2

        if len(pos1.shape) == 2:
            numFrames = 1
            num_pos1 = pos1.shape[0]
            num_pos2 = pos2.shape[0]
            dims = pos1.shape[1]
        elif len(pos1.shape) == 3:
            numFrames = pos1.shape[0]
            num_pos1 = pos1.shape[1]
            num_pos2 = pos2.shape[0]
            dims = pos1.shape[2]

        flag = numBoxes <= 3
        if np.all(flag):
            point_idx = np.arange(num_pos1)
            dip_idx = np.arange(num_pos2)
            p1 = np.repeat(point_idx,num_pos2)
            p2 = np.tile(dip_idx,num_pos1)
            return p1,p2
        elif np.any(flag):
            pos1 = pos1[:,~flag]
            pos2 = pos2[:,~flag]
            numBoxes = numBoxes[~flag]
            cutoff = cutoff[~flag]
            dims = np.count_nonzero(~flag)

        point_indices = (pos1/cutoff).astype(int)
        if not np.iterable(numBoxes):
            numBoxes = np.array([numBoxes]*dims)
        boxes = {}
        count = np.zeros(numBoxes)
        for i,idx in enumerate(point_indices):
            index = tuple(idx.tolist())
            if index not in boxes:
                boxes[index] = list()
            boxes[index].append(int(i))
            count[index] += 1

        P1,P2 = [],[]
        offset = np.array([np.arange(-1,2) for i in range(dims)]).T
        pos2_indices = (pos2/cutoff).astype(int)
        for p1,idx in enumerate(pos2_indices):
            offsets = (idx+offset)%numBoxes
            for off in itertools.product(*offsets.T):
                if count[off] == 0:
                    continue
                p2s = boxes[off]
                P1 += [p1]*len(p2s)
                P2 += (p2s)
        P1 = np.array(P1)
        P2 = np.array(P2)
        return P2,P1
    # }}}
# }}}
