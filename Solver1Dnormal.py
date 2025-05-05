# -*- coding: utf-8 -*-


# Solver sous-critique uniquement

g = 9.81

import warnings
# fsolve can produce warnings. This line turns them into an Exception
#warnings.simplefilter("error", RuntimeWarning)

warnings.simplefilter("ignore", RuntimeWarning)

from scipy.optimize import fsolve
from scipy.optimize import minimize

def manning_solver(cs):


    def equations(y):
        R = (cs.width * y) / (cs.width + 2 * y)
        manning = (y * cs.width * R ** (2. / 3.) * cs.s_valid ** 0.5) / cs.n - cs.Q
        return manning

    cs.y_valid = fsolve(equations, 1)[0]
    cs.R_valid = (cs.width * cs.y_valid) / (cs.width + 2 * cs.y_valid)
    cs.ycrit_valid = (cs.Q / (cs.width * g ** 0.5)) ** (2. / 3.)
    cs.v_valid = cs.Q / (cs.width * cs.y_valid)
    cs.h_valid = cs.z + cs.y_valid + cs.v_valid ** 2 / (2 * g)
    #cs_tosolve.h = cs_tosolve.z + cs_tosolve.y
    cs.Fr_valid = cs.v_valid / (g * cs.y_valid) ** 0.5
    cs.ws_valid = cs.z + cs.y_valid


def cs_solver(cs_up, cs_down):


    cs_tosolve = cs_up
    cs_ref = cs_down

    if cs_down.reach == cs_up.reach:
        localdist = (cs_up.dist - cs_down.dist)
    else:
        localdist = cs_down.reach.length - cs_down.dist + cs_up.dist

    # premier estimé : y = y_crit
    cs_tosolve.ycrit_valid = (cs_tosolve.Q / (cs_tosolve.width * g ** 0.5)) ** (2. / 3.)

    def equations(y):

        # if y < cs_tosolve.ycrit_valid:
        #     # constraint simulation
        #     return 9999
        R = (cs_tosolve.width * y) / (cs_tosolve.width + 2 * y)
        v = cs_tosolve.Q / (cs_tosolve.width * y)
        h = cs_tosolve.z + y
        # with kinetic energy?
        #h = h + (v ** 2) / (2 * g)
        s = (cs_tosolve.n ** 2 * v ** 2) / (R ** (4. / 3.))
        friction_h = localdist * s
        #friction_h = localdist * (s + cs_ref.s) / 2.
        energy = cs_ref.h_valid + friction_h - h
        energy = abs(energy)
        return energy

    res = minimize(equations, cs_tosolve.ycrit_valid, method='Nelder-Mead', bounds=[(cs_tosolve.ycrit_valid, None)], options={'xatol': 1e-3, 'fatol': 1e-3})
    # res, dict, ier, msg = fsolve(equations, cs_tosolve.ycrit, full_output=True)
    # ## if ier != 1, an error occured.
    # if ier != 1:
    #     cs_tosolve.y = 99
    # else:
    #     cs_tosolve.y = res[0]  # actual result of the solver

    cs_tosolve.y_valid = res.x[0]
    cs_tosolve.R_valid = (cs_tosolve.width * cs_tosolve.y_valid) / (cs_tosolve.width + 2 * cs_tosolve.y_valid)
    cs_tosolve.v_valid = cs_tosolve.Q / (cs_tosolve.width * cs_tosolve.y_valid)
    #cs_tosolve.h = cs_tosolve.z + cs_tosolve.y + cs_tosolve.v ** 2 / (2 * g)
    cs_tosolve.h_valid = cs_tosolve.z + cs_tosolve.y_valid
    cs_tosolve.s_valid = (cs_tosolve.n ** 2 * cs_tosolve.v_valid ** 2) / (cs_tosolve.R_valid ** (4. / 3.))
    cs_tosolve.Fr_valid = cs_tosolve.v_valid / (g * cs_tosolve.y_valid) ** 0.5
    cs_tosolve.ws_valid = cs_tosolve.z + cs_tosolve.y_valid

