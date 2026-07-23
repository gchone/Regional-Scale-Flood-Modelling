import warnings
warnings.simplefilter("ignore", RuntimeWarning)
from scipy.optimize import fsolve, minimize_scalar
g = 9.81

def manning_solver(cs):
    def equations(y):
        R = (cs.width * y) / (cs.width + 2 * y)
        return (y * cs.width * R ** (2. / 3.) * cs.s ** 0.5) / cs.n - cs.Q
    cs.y  = fsolve(equations, 1)[0]
    cs.R  = (cs.width * cs.y) / (cs.width + 2 * cs.y)
    cs.v  = cs.Q / (cs.width * cs.y)
    cs.z  = cs.wslidar - cs.y
    cs.h  = cs.wslidar + cs.v ** 2 / (2 * g)
    cs.Fr = cs.v / (g * cs.y) ** 0.5

def cs_solver(cs_up, cs_down, min_slope):
    cs_tosolve = cs_down
    cs_ref     = cs_up
    if cs_down.reach == cs_up.reach:
        localdist = float(cs_up.dist - cs_down.dist)
    else:
        localdist = float(
            cs_down.reach.feature.geometry().length() - cs_down.dist + cs_up.dist
        )
    if (cs_up.wslidar - cs_down.wslidar) / localdist <= min_slope:
        cs_tosolve.solver = "min_slope"
        h_ref = cs_up.h + localdist * (
            min_slope - (cs_up.wslidar - cs_down.wslidar) / localdist
        )
    else:
        h_ref = cs_up.h
    cs_tosolve.ycrit = (cs_tosolve.Q / (cs_tosolve.width * g ** 0.5)) ** (2. / 3.)

    def equations(y):
        if y < cs_tosolve.ycrit:
            return float('inf')
        R = (cs_tosolve.width * y) / (cs_tosolve.width + 2 * y)
        v = cs_tosolve.Q / (cs_tosolve.width * y)
        s = (cs_tosolve.n ** 2 * v ** 2) / (R ** (4. / 3.))
        h = cs_tosolve.wslidar + v ** 2 / (2 * g)
        return abs(localdist * s + h - h_ref)
    y_lo = cs_tosolve.ycrit * 1.001
    y_hi = y_lo * 2.0
    res = minimize_scalar(
        equations, method='brent', bracket=(y_lo, y_hi), tol=1e-3,
    )
    cs_tosolve.y  = res.x
    cs_tosolve.R  = (cs_tosolve.width * cs_tosolve.y) / (cs_tosolve.width + 2 * cs_tosolve.y)
    cs_tosolve.v  = cs_tosolve.Q / (cs_tosolve.width * cs_tosolve.y)
    cs_tosolve.z  = cs_tosolve.wslidar - cs_tosolve.y
    cs_tosolve.s  = (cs_tosolve.n ** 2 * cs_tosolve.v ** 2) / (cs_tosolve.R ** (4. / 3.))
    cs_tosolve.h  = cs_tosolve.wslidar + cs_tosolve.v ** 2 / (2 * g)
    cs_tosolve.Fr = cs_tosolve.v / (g * cs_tosolve.y) ** 0.5
    return res