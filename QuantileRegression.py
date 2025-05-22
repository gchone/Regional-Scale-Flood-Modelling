# -*- coding: utf-8 -*-

import numpy as np
import scipy.sparse
import scipy.optimize
import math

def QuantileCarving(listcs, prevcs, messages, tau=0.5):
    # This quantile carving process comes from :
    #    Schwanghart, W., Scherler, D., 2017. Bumps in river profiles:
    #    uncertainty assessment and smoothing using quantile regression
    #    techniques. Earth Surface Dynamics, 5, 821-839.
    #    [DOI: 10.5194/esurf-5-821-2017]
    # Code was adapted from their Matlab code:
    # https://github.com/wschwanghart/topotoolbox/
    #
    # A new attribute with the resulting water surface, ztosmooth, is added to the cross-sections in listcs
        
    # Converting the listcs into two arrays:
    # x and z are arrays of the same size with the distance and the elevations values
    #x = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    #z = np.array([1., 2., 3., 2., 5., 4.])

    if prevcs is None:
        minz = -math.inf
    else:
        minz = prevcs.ztosmooth

    reachdist = 0
    x = []
    z = []
    lastreach = None
    for cs in listcs:
        if lastreach is not None and cs.reach != lastreach:
            reachdist += lastreach.length
        x.append(cs.dist + reachdist)
        z.append(max(cs.z_forws, minz))  # "Fill" with the downstream z value (so z never gets lower)
        lastreach = cs.reach
    x = np.array(x)
    z = np.array(z)

    n = len(listcs)

    #n = 6
    ix = range(1, n)
    ixc = range(0, n-1)
    #ix = np.array([1, 2, 3, 4, 5])
    #ixc = np.array([0, 1, 2, 3, 4])

    f = [tau*np.ones((n, 1)),(1-tau)*np.ones((n, 1)),np.zeros((n, 1))]
    f = np.vstack(f)

    Aeq = scipy.sparse.hstack([scipy.sparse.identity(n), -scipy.sparse.identity(n), scipy.sparse.identity(n)])
    #Aeq = scipy.sparse.csr_matrix.todense(Aeq)

    beq = z

    lb = [0.]*(2*n)
    lb.extend([-math.inf]*n)
    bounds = [(lower, None) for lower in lb]

    d = 1./(x[ix]-x[ixc])

    Atmp = scipy.sparse.csr_matrix(np.zeros((n, n * 2)))
    Atmp2 = scipy.sparse.coo_matrix((d, (ix, ixc)), shape=(n, n)) - scipy.sparse.coo_matrix((d, (ix, ix)), shape=(n, n))
    A = scipy.sparse.hstack([Atmp, Atmp2])
    #A = scipy.sparse.csr_matrix.todense(A)
    b = np.zeros((n,1))

    output = scipy.optimize.linprog(f, A, b, Aeq, beq, bounds=bounds,
                           method='highs', callback=None)

    if output.status>0:
        messages.addWarningMessage("Quantile regression failure, check results for potential obvious error")
    newz = output.x[-n:]

    for i in range(0, n):
        listcs[i].ztosmooth = newz[i]


