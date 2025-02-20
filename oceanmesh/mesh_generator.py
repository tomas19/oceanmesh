import datetime
import logging
import os
import time

import matplotlib.pyplot as plt
import matplotlib.tri as tri
import numpy as np
import scipy.sparse as spsparse
from _delaunay_class import DelaunayTriangulation as DT
from _fast_geometry import unique_edges

from .clean import _external_topology
from .edgefx import multiscale_sizing_function
from .fix_mesh import fix_mesh
from .grid import Grid
from .signed_distance_function import Domain, multiscale_signed_distance_function

logger = logging.getLogger(__name__)

__all__ = [
    "generate_mesh",
    "generate_multiscale_mesh",
    "plot_mesh_connectivity",
    "plot_mesh_bathy",
    "write_to_fort14",
    "write_to_t3s",
]


def write_to_fort14(
    points,
    cells,
    filepath,
    topobathymetry=None,
    project_name="Created with oceanmesh",
    flip_bathymetry=False,
):
    """
    Parameters
    -----------
    points (numpy.ndarray): An array of shape (np, 2) containing the x, y coordinates of the mesh nodes.
    cells (numpy.ndarray): An array of shape (ne, 3) containing the indices of the nodes that form each mesh element.
    filepath (str): The file path to write the fort.14 file to.
    topobathymetry (numpy.ndarray): An array of shape (np, 1) containing the topobathymetry values at each node.
    project_name (str): The name of the project to be written to the fort.14 file.
    flip_bathymetry (bool): If True, the bathymetry values will be multiplied by -1.

    Returns:
    --------
    points (numpy.ndarray): An array of shape (np, 2) containing the x, y coordinates of the mesh nodes.
    cells (numpy.ndarray): An array of shape (ne, 3) containing the indices of the nodes that form each mesh element.
    filepath (str): The file path to write the fort.14 file to.
    """
    logger.info("Exporting mesh to fort.14 file...")

    # Calculate number of nodes and elements
    npoints = np.size(points, 0)
    nelements = np.size(cells, 0)

    if topobathymetry is not None:
        assert (
            len(topobathymetry) == npoints
        ), "topobathymetry must be the same length as points"
    else:
        topobathymetry = np.zeros((npoints, 1))

    if flip_bathymetry:
        topobathymetry *= -1

    # Shift cell indices by 1 (fort.14 uses 1-based indexing)
    cells += 1

    # Open file for writing
    with open(filepath, "w") as f_id:
        # Write mesh name
        if flip_bathymetry:
            f_id.write(f"{project_name} (bathymetry flipped) \n")
        else:
            f_id.write(f"{project_name} \n")

        # Write number of nodes and elements
        np.savetxt(
            f_id,
            np.column_stack((nelements, npoints)),
            delimiter=" ",
            fmt="%i",
            newline="\n",
        )

        # Write node coordinates
        for k in range(npoints):
            np.savetxt(
                f_id,
                np.column_stack((k + 1, points[k][0], points[k][1], topobathymetry[k])),
                delimiter=" ",
                fmt="%i %f %f %f",
                newline="\n",
            )

        # Write element connectivity
        for k in range(nelements):
            np.savetxt(
                f_id,
                np.column_stack((k + 1, 3, cells[k][0], cells[k][1], cells[k][2])),
                delimiter=" ",
                fmt="%i %i %i %i %i ",
                newline="\n",
            )

        # Write zero for each boundary condition (4 total)
        for k in range(4):
            f_id.write("%d \n" % 0)

    return f"Wrote the mesh to {filepath}..."


def write_to_t3s(points, cells, filepath):
    """
    Write mesh data to a t3s file.

    Parameters:
    points (numpy.ndarray): An array of shape (np, 2) containing the x, y coordinates of the mesh nodes.
    cells (numpy.ndarray): An array of shape (ne, 3) containing the indices of the nodes that form each mesh element.
    filepath (str): The file path to write the t3s file to.

    Returns:
    None
    """
    logger.info("Exporting mesh to t3s file...")

    # Calculate number of nodes and elements
    npoints = np.size(points, 0)
    nelements = np.size(cells, 0)

    # Open file for writing
    with open(filepath, "w") as f_id:
        # Write header
        today = datetime.datetime.now()
        date_time = today.strftime("%m/%d/%Y, %H:%M:%S")
        t3head = (
            """#########################################################################\n
        :FileType t3s ASCII EnSim 1.0\n
        # Canadian Hydraulics Centre/National Research Council (c) 1998-2004\n
        # DataType 2D T3 Scalar Mesh\n
        #
        :Application BlueKenue\n
        :Version 3.0.44\n
        :WrittenBy pyoceanmesh\n
        :CreationDate """
            + date_time
            + """\n
        #
        #------------------------------------------------------------------------\n
        #
        :Projection Cartesian\n
        :Ellipsoid Unknown\n
        #
        :NodeCount """
            + str(npoints)
            + """\n
        :ElementCount """
            + str(nelements)
            + """\n
        :ElementType T3\n
        #
        :EndHeader"""
        )  # END HEADER
        t3head = os.linesep.join([s for s in t3head.splitlines() if s])
        f_id.write(t3head)
        f_id.write("\n")

        # Write node coordinates
        for k in range(npoints):
            np.savetxt(
                f_id,
                np.column_stack((points[k][0], points[k][1], 0.0)),
                delimiter=" ",
                fmt="%f %f %f",
                newline="\n",
            )

        # Write element connectivity
        for k in range(nelements):
            np.savetxt(
                f_id,
                np.column_stack((cells[k][0], cells[k][1], cells[k][2])),
                delimiter=" ",
                fmt="%i %i %i ",
                newline="\n",
            )

    return f"Wrote the mesh to {filepath}..."


def plot_mesh_connectivity(points, cells, show_plot=True):
    """Plot the mesh connectivity using matplotlib's triplot function.
    Parameters
    ----------

    points : numpy.ndarray
        A 2D array containing the x and y coordinates of the points.
    cells : numpy.ndarray
        A 2D array containing the connectivity information for the triangles.
    show_plot : bool, optional
        Whether to show the plot or not. The default is True.

    Returns
    -------
    ax : matplotlib.axes.Axes
        The axes object containing the plot.
    """
    triang = tri.Triangulation(points[:, 0], points[:, 1], cells)
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.triplot(triang)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title("Mesh connectivity")
    if show_plot:
        plt.show(block=False)
    return ax


def plot_mesh_bathy(points, bathymetry, connectivity, show_plot=True):
    """
    Create a tricontourf plot of the bathymetry data associated with the points,
    using the triangle connectivity information to plot the contours.

    Parameters
    ----------
    points : numpy.ndarray
        A 2D array containing the x and y coordinates of the points.
    bathymetry : numpy.ndarray
        A 1D array containing the bathymetry values associated with each point.
    connectivity : numpy.ndarray
        A 2D array containing the connectivity information for the triangles.
    show_plot : bool, optional
        Whether or not to display the plot. Default is True.

    Returns
    -------
    matplotlib.axes._subplots.AxesSubplot
        The axis handle of the plot.

    """
    # Create a Triangulation object using the points and connectivity table
    triangulation = tri.Triangulation(points[:, 0], points[:, 1], connectivity)

    # Create a figure and axis object
    fig, ax = plt.subplots(figsize=(10, 10))

    # Plot the tricontourf
    tricontourf = ax.tricontourf(triangulation, bathymetry, cmap="jet")

    # Add colorbar
    plt.colorbar(tricontourf)

    # Set axis labels
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")

    # Set title
    ax.set_title("Mesh Topobathymetry")

    # Show the plot if requested
    if show_plot:
        plt.show()

    return ax


def _parse_kwargs(kwargs):
    for key in kwargs:
        if key in {
            "nscreen",
            "max_iter",
            "seed",
            "pfix",
            "points",
            "domain",
            "edge_length",
            "bbox",
            "min_edge_length",
            "plot",
            "blend_width",
            "blend_polynomial",
            "blend_max_iter",
            "blend_nnear",
            "lock_boundary",
            "pseudo_dt",
        }:
            pass
        else:
            raise ValueError(
                "Option %s with parameter %s not recognized " % (key, kwargs[key])
            )


def _check_bbox(bbox):
    assert isinstance(bbox, tuple), "`bbox` must be a tuple"
    assert int(len(bbox) / 2), "`dim` must be 2"


def generate_multiscale_mesh(domains, edge_lengths, **kwargs):
    r"""Generate a 2D triangular mesh using callbacks to several
    sizing functions `edge_lengths` and several signed distance functions
    See the kwargs for `generate_mesh`.

    Parameters
    ----------
    domains: A list of function objects.
        A list of functions that takes a point and returns the signed nearest distance to the domain boundary Ω.
    edge_lengths: A function object.
        A list of functions that can evalulate a point and return a mesh size.
    \**kwargs:
        See below for kwargs in addition to the ones available for `generate_mesh`

    :Keyword Arguments:
        * *blend_width* (``float``) --
                The width of the element size transition region between nest and parent
        * *blend_polynomial* (``int``) --
                The rate of transition scales with 1/dist^blend_polynomial
        * *blend_max_iter* (``int``) --
                The number of mesh generation iterations to blend the nest and parent.
        * *blend_nnear* (``int``) --
                The number of nearest neighbors in the IDW interpolation.

    """
    assert (
        len(domains) > 1 and len(edge_lengths) > 1
    ), "This function takes a list of domains and sizing functions"
    assert len(domains) == len(
        edge_lengths
    ), "The same number of domains must be passed as sizing functions"
    opts = {
        "max_iter": 100,
        "seed": 0,
        "pfix": None,
        "points": None,
        "min_edge_length": None,
        "plot": 999999,
        "blend_width": 2500,
        "blend_polynomial": 2,
        "blend_max_iter": 20,
        "blend_nnear": 256,
        "lock_boundary": False,
    }
    opts.update(kwargs)
    _parse_kwargs(kwargs)

    master_edge_length, edge_lengths_smoothed = multiscale_sizing_function(
        edge_lengths,
        blend_width=opts["blend_width"],
        nnear=opts["blend_nnear"],
        p=opts["blend_polynomial"],
    )
    union, nests = multiscale_signed_distance_function(domains)
    _p = []
    global_minimum = 9999
    for domain_number, (sdf, edge_length) in enumerate(
        zip(nests, edge_lengths_smoothed)
    ):
        logger.info(f"--> Building domain #{domain_number}")
        global_minimum = np.amin([global_minimum, edge_length.hmin])
        _tmpp, _ = generate_mesh(sdf, edge_length, **kwargs)
        _p.append(_tmpp)

    _p = np.concatenate(_p, axis=0)

    # merge the two domains together
    logger.info("--> Blending the domains together...")
    _p, _t = generate_mesh(
        domain=union,
        edge_length=master_edge_length,
        min_edge_length=global_minimum,
        points=_p,
        max_iter=opts["blend_max_iter"],
        lock_boundary=True,
        **kwargs,
    )

    return _p, _t


def generate_mesh(domain, edge_length, **kwargs):
    r"""Generate a 2D triangular mesh using callbacks to a
        sizing function `edge_length` and signed distance function.

    Parameters
    ----------
    domain: A function object.
        A function that takes a point and returns the signed nearest distance to the domain boundary Ω.
    edge_length: A function object.
        A function that can evalulate a point and return a mesh size.
    \**kwargs:
        See below

    :Keyword Arguments:
        * *bbox* (``tuple``) --
            Bounding box containing domain extents. REQUIRED IF NOT USING :class:`edge_length`
        * *max_iter* (``float``) --
            Maximum number of meshing iterations. (default==50)
        * *seed* (``float`` or ``int``) --
            Psuedo-random seed to initialize meshing points. (default==0)
        * *pfix* (`array-like`) --
            An array of points to constrain in the mesh. (default==None)
        * *min_edge_length* (``float``) --
            The minimum element size in the domain. REQUIRED IF NOT USING :class:`edge_length`
        * *plot* (``int``) --
            The mesh is visualized every `plot` meshing iterations.
        * *pseudo_dt* (``float``) --
            The pseudo time step for the meshing algorithm. (default==0.2)

    Returns
    -------
    points: array-like
        vertex coordinates of mesh
    t: array-like
        mesh connectivity table.

    """
    _DIM = 2
    opts = {
        "max_iter": 50,
        "seed": 0,
        "pfix": None,
        "points": None,
        "min_edge_length": None,
        "plot": 999999,
        "lock_boundary": False,
        "pseudo_dt": 0.2,
    }
    opts.update(kwargs)
    _parse_kwargs(kwargs)

    fd, bbox = _unpack_domain(domain, opts)
    fh, min_edge_length = _unpack_sizing(edge_length, opts)

    _check_bbox(bbox)
    bbox = np.array(bbox).reshape(-1, 2)

    assert min_edge_length > 0, "`min_edge_length` must be > 0"

    assert opts["max_iter"] > 0, "`max_iter` must be > 0"
    max_iter = opts["max_iter"]

    np.random.seed(opts["seed"])

    L0mult = 1 + 0.4 / 2 ** (_DIM - 1)
    delta_t = opts["pseudo_dt"]
    geps = 1e-3 * np.amin(min_edge_length)
    deps = np.sqrt(np.finfo(np.double).eps)  # * np.amin(min_edge_length)

    pfix, nfix = _unpack_pfix(_DIM, opts)
    lock_boundary = opts["lock_boundary"]

    if opts["points"] is None:
        p = _generate_initial_points(
            min_edge_length,
            geps,
            bbox,
            fh,
            fd,
            pfix,
        )
    else:
        p = opts["points"]

    N = p.shape[0]

    assert N > 0, "No vertices to mesh with!"

    logger.info(
        f"Commencing mesh generation with {N} vertices will perform {max_iter} iterations."
    )

    for count in range(max_iter):
        start = time.time()

        # (Re)-triangulation by the Delaunay algorithm
        dt = DT()
        dt.insert(p.ravel().tolist())

        # Get the current topology of the triangulation
        p, t = _get_topology(dt)

        ifix = []
        if lock_boundary:
            _, bpts = _external_topology(p, t)
            for fix in bpts:
                ifix.append(_closest_node(fix, p))
                nfix = len(ifix)

        # Find where pfix went
        if nfix > 0:
            for fix in pfix:
                ind = _closest_node(fix, p)
                ifix.append(ind)
                p[ind] = fix

        # Remove points outside the domain
        t = _remove_triangles_outside(p, t, fd, geps)

        # Number of iterations reached, stop.
        if count == (max_iter - 1):
            p, t, _ = fix_mesh(p, t, dim=_DIM, delete_unused=True)
            logger.info("Termination reached...maximum number of iterations.")
            return p, t

        # Compute the forces on the bars
        Ftot = _compute_forces(p, t, fh, min_edge_length, L0mult)

        # Force = 0 at fixed points
        Ftot[:nfix] = 0

        # Update positions
        p += delta_t * Ftot

        # Bring outside points back to the boundary
        p = _project_points_back(p, fd, deps)

        # Show the user some progress so they know something is happening
        maxdp = delta_t * np.sqrt((Ftot**2).sum(1)).max()

        logger.info(
            f"Iteration #{count+1}, max movement is {maxdp}, there are {len(p)} vertices and {len(t)}"
        )

        end = time.time()
        logger.info(f"Elapsed wall-clock time {end-start} seconds")


def _unpack_sizing(edge_length, opts):
    if isinstance(edge_length, Grid):
        fh = edge_length.eval
        min_edge_length = edge_length.hmin
    elif callable(edge_length):
        fh = edge_length
        min_edge_length = opts["min_edge_length"]
    else:
        raise ValueError(
            "`edge_length` must either be a function or a `edge_length` object"
        )
    return fh, min_edge_length


def _unpack_domain(domain, opts):
    if isinstance(domain, Domain):
        bbox = domain.bbox
        fd = domain.eval
    elif callable(domain):
        bbox = opts["bbox"]
        fd = domain
    else:
        raise ValueError(
            "`domain` must be a function or a :class:`signed_distance_function object"
        )
    return fd, bbox


def _get_bars(t):
    """Describe each bar by a unique pair of nodes"""
    bars = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    return unique_edges(bars)


# Persson-Strang
def _compute_forces(p, t, fh, min_edge_length, L0mult):
    """Compute the forces on each edge based on the sizing function"""
    N = p.shape[0]
    bars = _get_bars(t)
    barvec = p[bars[:, 0]] - p[bars[:, 1]]  # List of bar vectors
    L = np.sqrt((barvec**2).sum(1))  # L = Bar lengths
    L[L == 0] = np.finfo(float).eps
    hbars = fh(p[bars].sum(1) / 2)
    L0 = hbars * L0mult * ((L**2).sum() / (hbars**2).sum()) ** (1.0 / 2)
    F = L0 - L
    F[F < 0] = 0  # Bar forces (scalars)
    Fvec = (
        F[:, None] / L[:, None].dot(np.ones((1, 2))) * barvec
    )  # Bar forces (x,y components)
    Ftot = _dense(
        bars[:, [0] * 2 + [1] * 2],
        np.repeat([list(range(2)) * 2], len(F), axis=0),
        np.hstack((Fvec, -Fvec)),
        shape=(N, 2),
    )
    return Ftot


# Bossen-Heckbert
# def _compute_forces(p, t, fh, min_edge_length, L0mult):
#    """Compute the forces on each edge based on the sizing function"""
#    N = p.shape[0]
#    bars = _get_bars(t)
#    barvec = p[bars[:, 0]] - p[bars[:, 1]]  # List of bar vectors
#    L = np.sqrt((barvec ** 2).sum(1))  # L = Bar lengths
#    L[L == 0] = np.finfo(float).eps
#    hbars = fh(p[bars].sum(1) / 2)
#    L0 = hbars * L0mult * (np.nanmedian(L) / np.nanmedian(hbars))
#    LN = L / L0
#    F = (1 - LN ** 4) * np.exp(-(LN ** 4)) / LN
#    Fvec = (
#        F[:, None] / LN[:, None].dot(np.ones((1, 2))) * barvec
#    )  # Bar forces (x,y components)
#    Ftot = _dense(
#        bars[:, [0] * 2 + [1] * 2],
#        np.repeat([list(range(2)) * 2], len(F), axis=0),
#        np.hstack((Fvec, -Fvec)),
#        shape=(N, 2),
#    )
#    return Ftot


def _dense(Ix, J, S, shape=None, dtype=None):
    """
    Similar to MATLAB's SPARSE(I, J, S, ...), but instead returning a
    dense array.
    """

    # Advanced usage: allow J and S to be scalars.
    if np.isscalar(J):
        x = J
        J = np.empty(Ix.shape, dtype=int)
        J.fill(x)
    if np.isscalar(S):
        x = S
        S = np.empty(Ix.shape)
        S.fill(x)

    # Turn these into 1-d arrays for processing.
    S = S.flat
    II = Ix.flat
    J = J.flat
    return spsparse.coo_matrix((S, (II, J)), shape, dtype).toarray()


def _remove_triangles_outside(p, t, fd, geps):
    """Remove vertices outside the domain"""
    pmid = p[t].sum(1) / 3  # Compute centroids
    return t[fd(pmid) < -geps]  # Keep interior triangles


def _project_points_back(p, fd, deps):
    """Project points outsidt the domain back within"""
    d = fd(p)
    ix = d > 0  # Find points outside (d>0)
    if ix.any():

        def _deps_vec(i):
            a = [0] * 2
            a[i] = deps
            return a

        try:
            dgrads = [
                (fd(p[ix] + _deps_vec(i)) - d[ix]) / deps for i in range(2)
            ]  # old method
        except ValueError:  # an error is thrown if all points in fd are outside
            # bbox domain, so instead calulate all fd and then
            # take the solely ones outside domain
            dgrads = [(fd(p + _deps_vec(i)) - d) / deps for i in range(2)]
            dgrads = list(np.array(dgrads)[:, ix])
        dgrad2 = sum(dgrad**2 for dgrad in dgrads)
        dgrad2 = np.where(dgrad2 < deps, deps, dgrad2)
        p[ix] -= (d[ix] * np.vstack(dgrads) / dgrad2).T  # Project
    return p


def _generate_initial_points(min_edge_length, geps, bbox, fh, fd, pfix):
    """Create initial distribution in bounding box (equilateral triangles)"""
    p = np.mgrid[
        tuple(slice(min, max + min_edge_length, min_edge_length) for min, max in bbox)
    ].astype(float)
    p = p.reshape(2, -1).T
    r0 = fh(p)
    r0m = np.min(r0[r0 >= min_edge_length])
    p = p[np.random.rand(p.shape[0]) < r0m**2 / r0**2]
    p = p[fd(p) < geps]  # Keep only d<0 points
    return np.vstack(
        (
            pfix,
            p,
        )
    )


def _dist(p1, p2):
    """Euclidean distance between two sets of points"""
    return np.sqrt(((p1 - p2) ** 2).sum(1))


def _unpack_pfix(dim, opts):
    """Unpack fixed points"""
    pfix = np.empty((0, dim))
    nfix = 0
    if opts["pfix"] is not None:
        pfix = np.array(opts["pfix"], dtype="d")
        nfix = len(pfix)
        logger.info(f"Constraining {nfix} fixed points..")
    return pfix, nfix


def _get_topology(dt):
    """Get points and entities from :clas:`CGAL:DelaunayTriangulation2/3` object"""
    return dt.get_finite_vertices(), dt.get_finite_cells()


def _closest_node(node, nodes):
    nodes = np.asarray(nodes)
    deltas = nodes - node
    dist_2 = np.einsum("ij,ij->i", deltas, deltas)
    return np.argmin(dist_2)
