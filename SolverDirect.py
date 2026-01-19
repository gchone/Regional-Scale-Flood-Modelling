# -*- coding: utf-8 -*-

# Solver sous-critique uniquement

g = 9.81
#Froude_limite = 0.94
import warnings
warnings.simplefilter("ignore", RuntimeWarning)

from scipy.optimize import fsolve
from scipy.optimize import minimize_scalar
from scipy.optimize import minimize

def manning_solver(cs):

    def equations(y):
        R = (cs.width * y) / (cs.width + 2 * y)
        manning = (y * cs.width * R ** (2. / 3.) * cs.s ** 0.5) / cs.n - cs.Q
        return manning

    cs.y = fsolve(equations, 1)[0]
    cs.R = (cs.width * cs.y) / (cs.width + 2 * cs.y)
    cs.ycrit = (cs.Q / (cs.width * g ** 0.5)) ** (2. / 3.)

    cs.v = cs.Q / (cs.width * cs.y)
    cs.z = cs.wslidar - cs.y
    cs.h = cs.wslidar
    # with kinetic energy?
    cs.h = cs.h + cs.v ** 2 / (2 * g)
    cs.Fr = cs.v / (g * cs.y) ** 0.5


def cs_solver(cs, min_slope, method):
    # This function is an inverse 1D hydraulic solver, using Manning's and Bernoulli's equations to computed flow at a
    # downstream cross-section, knowing the conditions upstream
    # Inverse problem version (i.e. given ws, find z)

    # Compute the critical depth at each cross-section
    for i in range(len(cs.listtosolve) - 1):
        cs_down = cs.listtosolve[i + 1]
        # the solver starts at y = y_crit
        cs_down.ycrit = (cs_down.Q / (cs_down.width * g ** 0.5)) ** (2. / 3.)

    # In 2-XS mode, in parts where the water surface is not smoothed, with a succession of steep and almost flat slopes, the solver can
    # have converge to the maximum depth values. While this is technically correct (not a convergence issue), it is not
    # realistic. To avoid this, the 2-XS mode is removed is the water surface slope is decreasing
    # This process might be needed to be review if a smoothing by penalization is implemented
    if len(cs.listtosolve) == 3:
        ws_slope_1 = (cs.listtosolve[0].wslidar - cs.listtosolve[1].wslidar) / cs.listtosolve[1].localdist
        ws_slope_2 = (cs.listtosolve[1].wslidar - cs.listtosolve[2].wslidar) / cs.listtosolve[2].localdist
        if ws_slope_2 < ws_slope_1:
            cs.listtosolve.pop(2)

    def equations(y):
        # For a given flow depth y, the difference between the resultant energy (potential energy, i.e. water surface
        # elevation, plus kinetic energy, plus energy loss by friction) and the energy computed upstream is computed.
        # This function is used by fsolve, that tries to find y so that dif_energy = 0


        dif_energy = []
        for i in range(len(cs.listtosolve) - 1):

            cs_down = cs.listtosolve[i + 1]
            cs_up = cs.listtosolve[i]
            if (cs_up.wslidar - cs_down.wslidar) / cs_down.localdist <= min_slope:
                cs_down.solver = "min_slope"
                h_ref = cs_up.h + cs_down.localdist * (
                        min_slope - (cs_up.wslidar - cs_down.wslidar) / cs_down.localdist)
            else:
                h_ref = cs_up.h

            # y[i] = max(y[i], ycrit[i])
            R = (cs_down.width * y[i]) / (cs_down.width + 2 * y[i])
            v = cs_down.Q / (cs_down.width * y[i])
            s = (cs_down.n ** 2 * v ** 2) / (R ** (4. / 3.))
            h = cs_down.wslidar
            h = h + v ** 2 / (2 * g)  # add kinetic energy
            cs_down.h = h
            cs_down.s = s
            Fr = v / (g * y[i]) ** 0.5
            # slope calculation:
            friction_h = cs_down.localdist * (s + cs_up.s) / 2.
            if len(cs.listtosolve) - 1 == 1:
                # Friction is based and the downstream computed slope only if depth = 1 (necessary for convergence)
                friction_h = cs_down.localdist * s
            dif_energy.append(friction_h + h - h_ref)
            # dif_energy[i] = abs(dif_energy[i])
            if i > 0:
                cs_up_z = cs_up.wslidar - y[i - 1]
            else:
                cs_up_z = cs_up.z
            # if bed_smoothing:
            #     # Working:
            #     # dif_energy[i] = math.exp(abs(dif_energy[i])) + math.exp(20 * (1 - Fr)) * abs(cs_down.wslidar - y[i] - cs_up_z) / (
            #     #             cs_down.localdist * 1000000000)
            #     # Better:
            #     dif_energy[i] = abs(dif_energy[i]) + (1 - Fr) * abs(cs_down.wslidar - y[i] - cs_up_z) / (
            #             cs_down.localdist * 20)
            # else:
            dif_energy[i] = abs(dif_energy[i])

        misfit = (sum([e ** 2 for e in dif_energy]))**0.5
        # misfit = sum(dif_energy)
        # print(misfit)
        return misfit

    # Constraints to avoid supercritical flow and limit max depth to the width
    #bounds = [(cs.listtosolve[i + 1].ycrit, cs.listtosolve[i + 1].width/10.) for i in range(len(cs.listtosolve) - 1)]
    # Change: If flow is highly subcritical, then the solver doesn't work (best estimation could be maximum allowed depth)
    # It's better to not constraint the minimum depth, and just let the solver find the best solution, then replace the
    # solution by the critical depth if the solution is below it.
    bounds = [(0, cs.listtosolve[i + 1].width) for i in range(len(cs.listtosolve) - 1)]
    # initial guess
    ycrit = [cs.listtosolve[i + 1].ycrit for i in range(len(cs.listtosolve) - 1)]

    res = minimize(equations, ycrit, method='Nelder-Mead',
                   bounds=bounds, options={'xatol': 1e-3, 'fatol': 1e-6})
    #res = minimize_scalar(equations, method='brent', tol=1e-3)
    #cs_tosolve.y = res.x
    cs.y = res.x[cs.position_in_list - 1]
    if cs.y < cs.ycrit:
        cs.y = cs.ycrit



    cs.R = (cs.width * cs.y) / (cs.width + 2 * cs.y)
    cs.v = cs.Q / (cs.width * cs.y)
    cs.z = cs.wslidar - cs.y
    cs.s = (cs.n ** 2 * cs.v ** 2) / (cs.R ** (4. / 3.))
    cs.h = cs.wslidar
    cs.h = cs.h + cs.v ** 2 / (2 * g)  # add kinetic energy
    cs.Fr = cs.v / (g * cs.y) ** 0.5

    return res






