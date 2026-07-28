import numpy as np
import warnings
import matplotlib.pyplot as plt

tol = 10
zero_tol = 10**(-5)
class Edge():# {{{
    count = 0
    def __init__(self,p1,p2,owners=None):# {{{
        p1 = np.round(p1,tol)
        p2 = np.round(p2,tol)
        self.p1 = p1
        self.p2 = p2
        
        self.m,self.b = self._calc_line()
        self.count = Edge.count
        Edge.count += 1
        if owners is None:
            self.owners = []
        elif not isinstance(owners,list):
            self.owners = [owners]
        else:
            self.owners = owners
        return# }}}
    def add_owner(self,cell_id):# {{{
        self.owners.append(cell_id)
        return# }}}
    def get_intercept(self,m,b):# {{{
        if np.abs(self.m) == np.inf or np.abs(m) == np.inf:
            if np.abs(m) == np.inf:
                x = b
                y = self.m*x + self.b
            else:
                x = self.p1[0]
                y = m*x + b
        else:
            x = (self.b-b)/(m-self.m)
            y = m*x + b
        return np.array([x,y])# }}}
    def update_point(self,pidx,point):# {{{
        if pidx == 0:
            self.p1 = point
        else:
            self.p2 = point
        self.m,self.b = self._calc_line()
        return# }}}
    def _calc_line(self):# {{{
        d = self.p1 - self.p2
        m = d[1]/d[0]
        b = self.p1[1] - self.p1[0]*m
        return m,b# }}}
    # }}}
class Cell():# {{{
    count = -4
    def __init__(self,pt,edges=None):# {{{
        self.pt = np.round(pt,tol)
        if edges is None:
            self.edges = dict()
        else:
            self.edges = {e.count:e for e in edges} 
        self.current = -1
        self.count = Cell.count
        Cell.count += 1
        return# }}}
    def compare_edges(self,pt,plot,part_idx,cell_idx):# {{{

        to_remove = []
        pts = []
        edges = []
        p_idxs = []

        pt = np.round(pt,tol)
        mp,bp = self._calc_perp_bisector(pt)
        mp_is_inf = (np.abs(mp) == np.inf)
        pt_side,bp = self._calc_pt_side(pt,mp,bp,mp_is_inf)

        for idx,edge in enumerate(self.edges.values()):
            side_data = self._calc_edge_sides(edge,mp,bp,mp_is_inf,pt_side)
            self._parse_side_data(side_data,to_remove,pts,edges,p_idxs,edge,mp,bp)

        if not (len(pts) == 0 or len(pts) == 2):
            raise Exception(f"Found {len(pts)} crossing points")

        return [pts,edges,p_idxs,self.count], to_remove
    #}}}
    def remove_edge(self,edge_idx):# {{{
        return self.edges.pop(edge_idx)# }}}
    def _calc_perp_bisector(self,pt):# {{{
        mid_pt = (self.pt + pt)/2
        d = pt-self.pt
        m = -(d[1]/d[0])**-1
        b = mid_pt[1] - m*mid_pt[0]
        return m,b# }}}
    def _calc_edge_sides(self,edge,mp,bp,mp_is_inf,pt_side):# {{{
        if mp_is_inf:
            e1_on_side = (edge.p1[0] < bp) == pt_side
            e1_null = np.abs(edge.p1[0]-bp)<zero_tol
            e2_on_side = (edge.p2[0] < bp) == pt_side
            e2_null = np.abs(edge.p2[0]-bp)<zero_tol
        else:
            e1 = (edge.p1[1]-bp - mp*edge.p1[0])
            e1_on_side = ((e1>0) == pt_side)
            e1_null = abs(e1)<zero_tol

            e2 = (edge.p2[1]-bp - mp*edge.p2[0])
            e2_on_side = ((e2>0) == pt_side)
            e2_null = abs(e2)<zero_tol
        return e1_on_side, e1_null, e2_on_side, e2_null# }}}
    def _parse_side_data(self,side_data,to_remove,pts,edges,p_idxs,edge,mp,bp):# {{{
        e1_on_side, e1_null, e2_on_side, e2_null = side_data
        if e2_null and e1_null:
            pass
        elif e2_null or e1_null:
            e_on_side = e1_on_side if e2_null else e2_on_side
            if e_on_side:
                to_remove.append([self.count,edge.count])
            else:
                p_idx = 0 if e1_null else 1
                new_point = edge.get_intercept(mp,bp)
                pts.append(new_point)
                edges.append(edge.count)
                p_idxs.append(p_idx)
        elif e1_on_side and e2_on_side:
            to_remove.append([self.count,edge.count])
        elif e1_on_side or e2_on_side:
            p_idx = 0 if e1_on_side else 1
            new_point = edge.get_intercept(mp,bp)
            pts.append(new_point)
            edges.append(edge.count)
            p_idxs.append(p_idx)
        else:
            pass
        return# }}}
    def _calc_pt_side(self,pt,mp,bp,mp_is_inf):# {{{
        mp_is_inf = (np.abs(mp) == np.inf)
        if mp_is_inf:
            t_pt = (pt[0] + self.pt[0])/2
            pt_side = pt[0] < t_pt
            bp = t_pt
        else:
            t_pt = pt[1]-bp - mp*pt[0]
            pt_side = t_pt > 0
        return pt_side, bp# }}}
    def __iter__(self):# {{{
        return self# }}}
    def __next__(self):# {{{
        self.current += 1
        if self.current < len(self.edges):
            return self.edges[self.current]
        self.current = -1
        raise StopIteration# }}}
    def __getitem__(self,key):# {{{
        return self.edges[key]# }}}
    def __setitem__(self,key,value):# {{{
        value.add_owner(self.count)
        self.edges[key]=value
    # }}}
    # }}}
class Voronoi_Analysis:
    """
    Performs 2D Voronoi cell tessellation and topology analysis on particle coordinate sets.

    Parameters
    ----------
    box : array_like, optional
        Simulation box dimensions [Lx, Ly]. If None, inferred from coordinate extrema.
    border_ratio : float, optional
        Fractional padding ratio for replicating border particles across periodic boundaries. Default is 0.0.
    """

    def __init__(self, box=None, border_ratio=0.0):
        self.box = box
        self.border_ratio = border_ratio

    def compute(self, pts, verbose=False):
        """
        Construct Voronoi cells and network topology for 2D points.

        Parameters
        ----------
        pts : ndarray
            2D particle coordinate array of shape (N, 2).
        verbose : bool, optional
            If True, prints progress during cell construction. Default is False.
        """
        with warnings.catch_warnings(action="ignore"):
            if self.box is None:
                box = self._calc_box()
            if np.any(pts < 0):
                pts = np.copy(pts) + self.box / 2
                self.adjusted_pts = True
            else:
                self.adjusted_pts = False
            self.num_particles = pts.shape[0]
            pts, border_idx = self._replicate_border(pts)
            if verbose:
                print(f"{pts.shape[0] - self.num_particles} border points added")

            self._initialize()
            for i, pt in enumerate(pts):
                if verbose and i % 100 == 0:
                    print(i)
                c = Cell(pt)
                to_add, to_remove = self._compute_add_remove(pt, i)
                new_verts, new_counts, new_pidx, new_cell = self._parse_add(to_add)
                self._add_new_edges(c, to_add, new_verts)
                self._truncate_edges(new_verts, new_pidx, new_cell)
                self._close_borders(c, new_verts, new_counts)
                self._remove_edges(to_remove)
                self.cells[c.count] = c
            self._remove_extra_cells()
            self._relabel_border_cells(border_idx)
        return

    def _plot(self):# {{{
        for idx,c in self.cells.items():
            if idx >= self.num_particles:
                break
            plt.scatter(*c.pt,color="k")
            for e in c.edges.values():
                A = np.array([e.p1,e.p2])
                plt.plot(*A.T,"k-")
        # }}}
    def _replicate_border(self,pts):# {{{
        pt_ratio = pts/self.box
        pt_idx = np.arange(self.num_particles)
        LR_flag = (pt_ratio[:,0] < self.border_ratio) | (pt_ratio[:,0] > (1-self.border_ratio))
        LR_pts = pts[LR_flag]
        LR_idx = pt_idx[LR_flag]
        LR_pts[:,0] += self.box[0]*(-1)**np.round(pt_ratio[:,0][LR_flag])
        TB_flag = (pt_ratio[:,1] < self.border_ratio) | (pt_ratio[:,1] > (1-self.border_ratio))
        TB_pts = pts[TB_flag]
        TB_idx = pt_idx[TB_flag]
        TB_pts[:,1] += self.box[1]*(-1)**np.round(pt_ratio[:,1][TB_flag])
        corner_flag = LR_flag & TB_flag
        corner_idx = pt_idx[corner_flag]
        corner_pts = pts[corner_flag] + self.box*(-1)**(np.round(pt_ratio[corner_flag]))
        border_pts = np.concatenate([LR_pts,TB_pts,corner_pts])
        border_idx = np.concatenate([LR_idx,TB_idx,corner_idx])
        pts = np.concatenate([pts,border_pts])
        return pts,border_idx# }}}
    def _calc_box(self,pts):# {{{
        mx = np.max(pts,axis=0)
        mn = np.min(pts,axis=0)
        box = mx - mn
        return box# }}}
    def _initialize(self):# {{{
        self.cells = dict()
        mid = self.box/2
        r = 1+self.border_ratio

        for i in range(2):
            for j in range(2):
                x = i*self.box[0] + (-1)**(i+1)*self.border_ratio*self.box[0]
                y = j*self.box[1] + (-1)**(j+1)*self.border_ratio*self.box[1]
                out = np.array([mid[0]+(-1)**(i+1)*r*self.box[0],mid[1]+(-1)**(j+1)*r*self.box[1]])
                A = np.array([mid[0],out[1]])
                B = np.array([out[0],mid[1]])

                c = Cell(np.array([x,y]))
                e1 = Edge(out,A)
                c[e1.count] = e1
                e2 = Edge(out,B)
                c[e2.count] = e2

                self.cells[c.count] = c

        left_border = mid[0] - r*self.box[0]
        e = Edge([left_border,mid[1]],[mid[0],mid[1]])
        self.cells[-4][e.count] = e
        self.cells[-3][e.count] = e

        right_border = mid[0] + r*self.box[0]
        e = Edge([right_border,mid[1]],[mid[0],mid[1]])
        self.cells[-2][e.count] = e
        self.cells[-1][e.count] = e

        bottom_border = mid[1] - r*self.box[1]
        e = Edge([mid[0],bottom_border],[mid[0],mid[1]])
        self.cells[-4][e.count] = e
        self.cells[-2][e.count] = e

        top_border = mid[1] + r*self.box[1]
        e = Edge([mid[0],top_border],[mid[0],mid[1]])
        self.cells[-3][e.count] = e
        self.cells[-1][e.count] = e
        # }}}
    def _compute_add_remove(self,pt,i):# {{{
        to_add = []
        to_remove = []
        for j,c in self.cells.items():
            try:
                add,remove = c.compare_edges(pt,self._plot,i,j)
            except Exception as err:
                raise err

            if len(add[0]) != 0:
                to_add.append(add)
            if len(remove) != 0:
                to_remove += remove
        return to_add, to_remove
    # }}}
    def _add_new_edges(self,c,to_add,new_verts):# {{{
        for pts,edge_idxs,p_idxs,cell_idx in to_add:
            e = Edge(new_verts[edge_idxs[0]],new_verts[edge_idxs[1]])
            self.cells[cell_idx][e.count] = e
            c[e.count] = e
        return# }}}
    def _truncate_edges(self,new_verts,new_pidx,new_cell):# {{{
        for edge_idx, new_pt in new_verts.items():
            pidx = new_pidx[edge_idx]
            cell_idx = new_cell[edge_idx]
            self.cells[cell_idx][edge_idx].update_point(pidx,new_pt)
        return
        # }}}
    def _close_borders(self,c,new_verts,new_counts):# {{{
        singles = []
        for edge_idx, new_pt in new_verts.items():
            if new_counts[edge_idx] == 1:
                singles.append(new_pt)

        for k in range(len(singles)):
            for l in range(k,len(singles)):
                if np.isclose(singles[k][0],singles[l][0]) or np.isclose(singles[k][1],singles[l][1]):
                    e = Edge(singles[k],singles[l])
            c[e.count] = e
        return# }}}
    def _remove_edges(self,to_remove):# {{{
        for cell_idx, edge_idx in to_remove:
            self.cells[cell_idx].remove_edge(edge_idx)
        return# }}}
    def _remove_extra_cells(self):# {{{
        for i in range(-4,0):
            self.cells.pop(i)
        for i in range(self.num_particles,len(self.cells)):
            self.cells.pop(i)
        return# }}}
    def _relabel_border_cells(self,border_idx):# {{{
        for idx,cell in self.cells.items():
            for e in cell.edges.values():
                for i in range(len(e.owners)):
                    owner_idx = e.owners[i]
                    if owner_idx >= self.num_particles:
                        e.owners[i] = border_idx[owner_idx-self.num_particles]
        return# }}}
    def _parse_add(self,to_add):# {{{
        new_verts = dict()
        new_counts = dict()
        new_pidx = dict()
        new_cell = dict()
        for pts,edge_idxs,p_idxs,cell_idx in to_add:
            for l in range(2):
                edge_idx = edge_idxs[l]
                if edge_idx in new_verts:
                    new_counts[edge_idx] += 1
                    continue
                new_verts[edge_idx] = pts[l]
                new_counts[edge_idx] = 1
                new_pidx[edge_idx] = p_idxs[l]
                new_cell[edge_idx] = cell_idx
        return new_verts,new_counts,new_pidx,new_cell
        # }}}
    def get_nlist(self):# {{{
        nlist = []
        for idx,cell in self.cells.items():
            for e in cell.edges.values():
                if len(e.owners) == 2:
                    nlist.append(e.owners)
        self.p1,self.p2 = np.array(nlist,dtype=int).T
        return self.p1,self.p2
    # }}}
    def get_border_cells(self):# {{{
        border_cells = set()
        for cell_idx,cell in self.cells.items():
            for e in cell.edges.values():
                if len(e.owners) == 1:
                    border_cells.add(cell_idx)

        self.border_cells = np.array(list(border_cells),dtype=int)
        return self.border_cells
    # }}}
    def get_cell_vertices(self):# {{{
        all_verts = []
        pts = []
        for c in self.cells.values():
            verts = []
            pts.append(c.pt)
            for e in c.edges.values():
                verts.append(e.p1)
                verts.append(e.p2)
            v = np.unique(verts,axis=0)
            v0 = v - np.average(v,axis=0)

            vL = v[v0[:,0]<=0]
            vL0 = v0[v0[:,0]<=0]
            theta = np.arctan(vL0[:,1]/vL0[:,0])
            flags = np.argsort(theta)
            vL = vL[flags]

            vR = v[v0[:,0]>=0]
            vR0 = v0[v0[:,0]>=0]
            theta = np.arctan(vR0[:,1]/vR0[:,0])
            flags = np.argsort(theta)
            vR = vR[flags]

            v = np.concatenate([vL,vR])
            if self.adjusted_pts:
                v -= self.box/2
            all_verts.append(v)

        return all_verts
    #}}}
# }}}
