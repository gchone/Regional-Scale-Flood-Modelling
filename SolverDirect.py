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
    cs.solver = "manning"


def cs_solver(cs, min_slope, method, max_delta_y):
    # This function is an inverse 1D hydraulic solver, using Manning's and Bernoulli's equations to computed flow at a
    # downstream cross-section, knowing the conditions upstream
    # Inverse problem version (i.e. given ws, find z)
    # cs has listtosolve as an attribute, with a list of adjacent cross-section, from upstream to downstream. In the current implementation, this list
    # always has a length of 3, with the assessed cross-section in the middle, and the one already known being the first.
    # Atttribute max_delta_y: maximum increase of water depth per meter. e.g: 40 -> max +200% of water depth for 5m spaced
    #   cross-section (compared to the upstream cross-section). This is used to avoid convergence to unrealistic
    #   solutions in case of steep slopes, when the solver is not working properly (in 2-XS mode).

    if method != "2-XS" and len(cs.listtosolve) == 3: # Deleting unused cross-section for "OVERSAMPLING" or "SIMPLE" methods
        # last cross-section is removed
        cs.listtosolve.pop(2)

    def equations(y):
        # For a given flow depth y, the difference between the resultant energy (potential energy, i.e. water surface
        # elevation, plus kinetic energy, plus energy loss by friction) and the energy computed upstream is computed.
        # This function is used by minimize, that tries to find y so that dif_energy is minimal

        dif_energy = []
        for i in range(len(cs.listtosolve) - 1):

            cs_tosolve = cs.listtosolve[i + 1]
            cs_ref = cs.listtosolve[i]
            localdist = cs_tosolve.localdist_up
            if i == 0:
                cs_ref.temp_h = cs_ref.h
                cs_ref.temp_s = cs_ref.s
            if abs(cs_ref.wslidar - cs_tosolve.wslidar) / localdist <= min_slope:
                cs_tosolve.solver = "min_slope"
                h_ref = cs_ref.temp_h + localdist * (
                        min_slope - (cs_ref.wslidar - cs_tosolve.wslidar) / localdist)
            else:
                h_ref = cs_ref.temp_h

            v = cs_tosolve.Q / (cs_tosolve.width * y[i])
            R = (cs_tosolve.width * y[i]) / (cs_tosolve.width + 2 * y[i])
            s = (cs_tosolve.n ** 2 * v ** 2) / (R ** (4. / 3.))
            h = cs_tosolve.wslidar
            h = h + v ** 2 / (2 * g)  # add kinetic energy
            cs_tosolve.temp_h = h
            cs_tosolve.temp_s = s
            # slope calculation:
            friction_h = localdist * (s + cs_ref.temp_s) / 2.
            if len(cs.listtosolve) - 1 == 1:
                # Friction is based and the downstream computed slope only if depth = 1 (necessary for convergence)
                friction_h = localdist * s

            dif_energy.append(friction_h + h - h_ref)

            # if bed_smoothing:
            #   if i > 0:
            #       cs_up_z = cs_ref.wslidar - y[i - 1]
            #   else:
            #       cs_up_z = cs_ref.z
            #   # Working:
            #   # dif_energy[i] = math.exp(abs(dif_energy[i])) + math.exp(20 * (1 - Fr)) * abs(cs_down.wslidar - y[i] - cs_up_z) / (
            #   #             cs_down.localdist * 1000000000)
            #   # Better:
            #   dif_energy[i] = abs(dif_energy[i]) + (1 - Fr) * abs(cs_down.wslidar - y[i] - cs_up_z) / (
            #           cs_down.localdist * 20)
            # else:
            dif_energy[i] = abs(dif_energy[i])

        misfit = (sum([e ** 2 for e in dif_energy]))**0.5
        # misfit = sum(dif_energy)
        # print(misfit)
        return misfit

    # Only the subcritical flow is computed, but the supercritical estimated nevertheless in reverse, and if it's a
    # better fit the critical depth is

    # Compute the critical depth at each cross-section
    for i in range(len(cs.listtosolve) - 1):
        cs_down = cs.listtosolve[i + 1]
        # the solver starts at y = y_crit
        cs_down.ycrit = (cs_down.Q / (cs_down.width * g ** 0.5)) ** (2. / 3.)
    # Find the best fit between critical depth and maximum allowed depth
    ycrit = [cs.listtosolve[i + 1].ycrit for i in range(len(cs.listtosolve) - 1)]     # initial guess
    if max_delta_y is not None:
        max_y = [max(cs.listtosolve[1].ycrit,min(cs.listtosolve[0].y*(1 + max_delta_y*cs.localdist_up/100.), cs.listtosolve[1].width))]
    else:
        max_y = [max(cs.listtosolve[1].ycrit, cs.listtosolve[1].width)]
    max_y.extend([cs.listtosolve[i + 1].width for i in range(1, len(cs.listtosolve) - 1)])
    bounds = [(cs.listtosolve[i + 1].ycrit,  max_y[i]) for i in range(len(cs.listtosolve) - 1)]
    res = minimize(equations, ycrit, method='Nelder-Mead',
                   bounds=bounds, options={'xatol': 1e-3, 'fatol': 1e-6})
    cs.solver = "regular"
    if max_delta_y is not None and res.x[cs.position_in_list - 1] == cs.listtosolve[0].y*max_delta_y*cs.localdist_up/100.:
        cs.solver = "max depth gradient"
    if res.x[cs.position_in_list - 1] == cs.listtosolve[1].width:
        cs.solver = "max depth"

    # Supercritical estimation
    bounds = [(0, cs.listtosolve[i + 1].ycrit) for i in range(len(cs.listtosolve) - 1)]
    res_super = minimize(equations, ycrit, method='Nelder-Mead',
                   bounds=bounds, options={'xatol': 1e-3, 'fatol': 1e-6})

    res = min([res, res_super] , key=lambda r: r.fun)

    cs.y = res.x[cs.position_in_list - 1]
    if cs.y < cs.ycrit:
        cs.y = cs.ycrit
        cs.solver = "critical"

    cs.R = (cs.width * cs.y) / (cs.width + 2 * cs.y)
    cs.v = cs.Q / (cs.width * cs.y)
    cs.z = cs.wslidar - cs.y
    cs.s = (cs.n ** 2 * cs.v ** 2) / (cs.R ** (4. / 3.))
    cs.h = cs.wslidar
    cs.h = cs.h + cs.v ** 2 / (2 * g)  # add kinetic energy
    cs.Fr = cs.v / (g * cs.y) ** 0.5

    return res






