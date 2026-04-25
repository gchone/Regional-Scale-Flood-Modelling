import math
import numpy as np
import scipy.sparse
import scipy.optimize


def quantile_carving(points_list, prev_pt, pts_dist, quantile=0.5, feedback=None):
    """
    Removes bumps in a water surface profile using quantile regression.
    Adds 'zws_quantilecarving' key to each dict in points_list in place.

    Based on:
        Schwanghart, W., Scherler, D., 2017. Bumps in river profiles:
        uncertainty assessment and smoothing using quantile regression
        techniques. Earth Surface Dynamics, 5, 821-839.
        [DOI: 10.5194/esurf-5-821-2017]
    Code adapted from their MATLAB implementation:
        https://github.com/wschwanghart/topotoolbox/

    Args:
        points_list : list of dicts — each dict must have 'dist' and 'z_forws' keys
        prev_pt     : dict or None — last point from downstream reach (provides min Z)
        quantile    : float — quantile for regression (default 0.5, use 0.2 for carving)
        feedback    : QgsProcessingFeedback or None
    """
    if prev_pt is None:
        min_z = -math.inf
    else:
        min_z = float(prev_pt.get("zws_quantilecarving", -math.inf))

    x = np.array([float(p[pts_dist]) for p in points_list])
    z = np.array([max(float(p["z_forws"]), min_z) for p in points_list])

    n = len(points_list)
    if n < 2:
        for pt in points_list:
            pt["zws_quantilecarving"] = float(pt["z_forws"])
        return

    ix  = range(1, n)
    ixc = range(0, n - 1)

    tau = quantile
    f = np.vstack([
        tau       * np.ones((n, 1)),
        (1 - tau) * np.ones((n, 1)),
        np.zeros((n, 1)),
    ])

    Aeq = scipy.sparse.hstack([
        scipy.sparse.identity(n),
        -scipy.sparse.identity(n),
        scipy.sparse.identity(n),
    ])
    beq = z

    lb = [0.0] * (2 * n) + [-math.inf] * n
    bounds = [(lower, None) for lower in lb]

    d    = 1.0 / (x[list(ix)] - x[list(ixc)])
    Atmp = scipy.sparse.csr_matrix(np.zeros((n, n * 2)))
    Atmp2 = (
        scipy.sparse.coo_matrix((d, (list(ix), list(ixc))), shape=(n, n))
        - scipy.sparse.coo_matrix((d, (list(ix), list(ix))), shape=(n, n))
    )
    A = scipy.sparse.hstack([Atmp, Atmp2])
    b = np.zeros((n, 1))

    output = scipy.optimize.linprog(
        f, A, b, Aeq, beq,
        bounds=bounds,
        method="highs",
    )

    if output.status > 0:
        msg = "Quantile regression failure — check results for potential errors"
        if feedback:
            feedback.pushWarning(msg)
        else:
            print(f"WARNING: {msg}")

    new_z = output.x[-n:]
    for i, pt in enumerate(points_list):
        pt["zws_quantilecarving"] = float(new_z[i])