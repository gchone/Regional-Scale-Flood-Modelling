# -*- coding: utf-8 -*-

# Solver sous-critique uniquement

g = 9.81
#Froude_limite = 0.94
import warnings
warnings.simplefilter("ignore", RuntimeWarning)

from scipy.optimize import fsolve
from scipy.optimize import minimize_scalar

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


def cs_solver(cs_up, cs_down, min_slope):


    cs_tosolve = cs_down
    cs_ref = cs_up

    if cs_down.reach == cs_up.reach:
        localdist = float(cs_up.dist - cs_down.dist)
    else:
        localdist = float(cs_down.reach.length - cs_down.dist + cs_up.dist)


    if (cs_up.wslidar - cs_down.wslidar)/localdist <= min_slope:
        cs_tosolve.solver = "min_slope"
        h_ref = cs_up.h + localdist * (min_slope - (cs_up.wslidar - cs_down.wslidar) / localdist)
    else:
        h_ref = cs_up.h

    # premier estimé : y = y_crit
    cs_tosolve.ycrit = (cs_tosolve.Q / (cs_tosolve.width * g ** 0.5)) ** (2. / 3.)


    def equations(y):

        if y < cs_tosolve.ycrit:
            # constraint simulation
            return float('inf')
        R = (cs_tosolve.width * y) / (cs_tosolve.width + 2 * y)
        v = cs_tosolve.Q / (cs_tosolve.width * y)
        s = (cs_tosolve.n ** 2 * v ** 2) / (R ** (4. / 3.))
        h = cs_tosolve.wslidar
        # with kinetic energy?
        h = h + v ** 2 / (2 * g)
        # slope calculation:
        #friction_h = localdist * (s+cs_ref.s)/2. # Friction can't be based on the average of slope, it leads to impossible to resolve cases
        friction_h = localdist * s
        energy = friction_h + h - h_ref
        energy = abs(energy)# + abs(cs_tosolve.wslidar - y - cs_ref.z)/(10*localdist)
        return energy

    res = minimize_scalar(equations, method='brent', tol=1e-3)

    # Example of possible smoothing: y is changed according to local Fr and variation of Fr
    # y = res.x[0]
    # v = cs_tosolve.Q / (cs_tosolve.width * y)
    # Fr = v / (g * y) ** 0.5
    # weight = max(Fr, min(2*(Fr-cs_up.Fr)/cs_up.Fr, 1))
    # cs_tosolve.y = weight*y + (1-weight)*cs_up.y

    cs_tosolve.y = res.x
    cs_tosolve.R = (cs_tosolve.width * cs_tosolve.y) / (cs_tosolve.width + 2 * cs_tosolve.y)
    cs_tosolve.v = cs_tosolve.Q / (cs_tosolve.width * cs_tosolve.y)
    cs_tosolve.z = cs_tosolve.wslidar - cs_tosolve.y
    cs_tosolve.s = (cs_tosolve.n ** 2 * cs_tosolve.v ** 2) / (cs_tosolve.R ** (4. / 3.))

    cs_tosolve.h = cs_tosolve.wslidar
    # with kinetic energy?
    cs_tosolve.h = cs_tosolve.h + cs_tosolve.v ** 2 / (2 * g)

    cs_tosolve.Fr = cs_tosolve.v / (g * cs_tosolve.y) ** 0.5



    return res






