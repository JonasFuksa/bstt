from math import comb

import numpy as np
import xerus as xe
from numpy.polynomial.legendre import legval
from rich.console import Console
from rich.table import Table

from misc import random_homogenous_polynomial, random_full
from als import ALS


# ==========
#  TRAINING
# ==========

N = int(1e3)  # number of samples

# print("Recover a polynomial")
# M = 6    # order
# # f = lambda xs: legval(xs[:,0], [0,0,1])  # L2(x0) * L0(x1) * L0(x2)
# # f = lambda xs: sum(legval(xs[:,m], [0,0,1]) for m in range(xs.shape[1]))
# # f = lambda xs: xs[:,0]**2  # x0**2 * L0(x1) * L0(x2) but x0**2 != L2(x0)
# # f = lambda xs: np.linalg.norm(xs, axis=1)**2
# f = lambda xs: np.pi + np.sum(xs, axis=1) + np.linalg.norm(xs, axis=1)**2 + np.sum(xs, axis=1)*np.linalg.norm(xs, axis=1)**2
# maxDegree = 3

print("Recover an exponential")
M = 6    # order
f = lambda xs: np.exp(-np.linalg.norm(xs, axis=1)**2)  #NOTE: This functions gets peakier for larger M!
maxDegree = 7

# print("Recover the mean of uniform Darcy")
# M = 20    # order
# z = np.load(".cache/darcy_uniform_mean.npz")
# assert N < len(z['values'])
# maxDegree = 5


def measures(_points, _degree):
    factors = np.sqrt(2*np.arange(_degree+1)+1)
    return legval(_points, np.diag(factors)).T


def residual(_bstts, _measures, _values):
    pred = sum(bstt.evaluate(_measures) for bstt in _bstts)
    return np.linalg.norm(pred -  _values) / np.linalg.norm(_values)


def recover_ml(_points, _values, _maxDegree, _maxIter=10, _targetResidual=1e-12):
    numSamples, order = _points.shape
    meas = measures(_points, _maxDegree)
    assert meas.shape == (order,numSamples,_maxDegree+1)
    bstts = [random_homogenous_polynomial([_maxDegree]*order, deg, 1) for deg in range(_maxDegree+1)]
    for bstt in bstts:
        bstt.assume_corePosition(order-1)
        while bstt.corePosition > 0: bstt.move_core('left')
        bstt.components[0] *= 1e-3/np.linalg.norm(bstt.components[0])
    print("="*80)
    res = np.inf
    for itr in range(_maxIter):
        print(f"Iteration: {itr}")
        for deg in range(_maxDegree+1):
            vals = _values - sum(bstt.evaluate(meas) for bstt in bstts[:deg]+bstts[deg+1:])
            solver = ALS(bstts[deg], meas, vals, _verbosity=0)
            solver.targetResidual = _targetResidual
            solver.run()
            bstts[deg] = solver.bstt
        old_res, res = res, residual(bstts, meas, _values)
        print(f"Residual: {res:.2e}")
        if old_res < res or res < _targetResidual: break
        if itr < _maxIter-1: print("-"*80)
    print("="*80)
    return bstts


try:
    points = z['samples'][:N]
    values = z['values'][:N]
except:
    points = 2*np.random.rand(N, M)-1
    values = f(points)
assert values.shape == (N,)
meas = measures(points, maxDegree)
assert meas.shape == (M,N,maxDegree+1)


bstts = recover_ml(points, values, maxDegree, _maxIter=20)
assert all(bstt.dimensions == bstts[0].dimensions for bstt in bstts[1:])


try:
    N_test = len(z['samples'])-N
    assert N_test > 0
    points_test = z['samples'][N:]
    values_test = z['values'][N:]
except:
    N_test = int(1e4)  # number of test samples
    points_test = 2*np.random.rand(N_test, M)-1
    values_test = f(points_test)
assert values_test.shape == (N_test,)
measures_test = measures(points_test, maxDegree)
assert measures_test.shape == (M,N_test,maxDegree+1)


def mlBSTT_dofs(_bstts):
    return sum(bstt.dofs() for bstt in _bstts)


def TT_dofs(_tt):
    return sum(_tt.get_component(pos).size for pos in range(_tt.order()))


def sparse_dofs():
    return comb(maxDegree+M, M)


def dense_dofs():
    return (maxDegree+1)**M


def to_xe(_bstts, _eps):
    ret = xe.TTTensor([maxDegree+1]*M)
    for bstt in _bstts:
        sm = xe.TTTensor(bstt.dimensions)
        for pos in range(bstt.order):
            sm.set_component(pos, xe.Tensor.from_ndarray(bstt.components[pos]))
        ret += sm
    ret.round(_eps)
    return ret


def from_xe(_tt):
    from bstt import BlockSparseTT
    from misc import block
    order = _tt.order()
    dimensions = _tt.dimensions
    ranks = [1] + _tt.ranks() + [1]
    blocks = [[block[0:ranks[m],0:dimensions[m],0:ranks[m+1]]] for m in range(order)]
    components = [_tt.get_component(m).to_ndarray() for m in range(order)]
    return BlockSparseTT(components, blocks)


bstt = random_full([maxDegree]*M, maxDegree+1)
solver = ALS(bstt, meas, values, _verbosity=1)
solver.targetResidual = 1e-12
solver.maxSweeps = 30
solver.run()
bstt = solver.bstt


console = Console()
table = Table(title=f"{maxDegree+1}-level BSTT reconstruction", title_style="bold", show_header=True, header_style="dim")
table.add_column("", style="dim", justify="left")
table.add_column("Error", justify="right")
table.add_column("Dofs", justify="right")
table.add_row("mlBSTT", f"{residual(bstts, measures_test, values_test):.2e}", f"{mlBSTT_dofs(bstts)}")
xett = to_xe(bstts, 1e-12)
table.add_row("as rounded TT (1e-12)", f"{residual([from_xe(xett)], measures_test, values_test):.2e}", f"{TT_dofs(xett)}")
xett = to_xe(bstts, 1e-8)
table.add_row("as rounded TT (1e-8)", f"{residual([from_xe(xett)], measures_test, values_test):.2e}", f"{TT_dofs(xett)}")
xett = to_xe(bstts, 1e-6)
table.add_row("as rounded TT (1e-6)", f"{residual([from_xe(xett)], measures_test, values_test):.2e}", f"{TT_dofs(xett)}")
table.add_row("dense TT", f"{residual([bstt], measures_test, values_test):.2e}", f"{mlBSTT_dofs([bstt])}")
table.add_row("sparse", f"", f"{sparse_dofs()}")
table.add_row("full", f"", f"{dense_dofs()}")
console.print(table)


def unslice(_block):
    assert all(slc.stop == slc.start+1 for  slc in _block)
    return tuple(slc.start for slc in _block)
