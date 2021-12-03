from math import comb, factorial

import numpy as np
from numpy.polynomial.legendre import legval,legmul,legint,legder
from numpy.polynomial.hermite_e import hermeval

from bstt import Block, BlockSparseTT, BlockSparseTTSystem
from als import ALS


class __block(object):
    def __getitem__(self, _slices):
        assert len(_slices) == 3 or len(_slices) == 4
        assert all(isinstance(slc, (int, slice)) for slc in _slices)
        def as_slice(_slc):
            if isinstance(_slc, slice):
                assert _slc.step in (None, 1) and 0 <= _slc.start < _slc.stop
                return _slc
            else:
                assert _slc >= 0
                return slice(_slc, _slc+1)
        return Block(as_slice(slc) for slc in _slices)
block = __block()


def random_polynomial(_univariateDegrees, _maxTotalDegree):
    assert _maxTotalDegree >= max(_univariateDegrees)  #TODO: This is only required due to unnecessary restrictions in BlockSparseTT.
    # Consider a coefficient tensor with dimensions [3,3,3,3] for a polynomial with (total) degree 2.
    # (Note that the space of univariate polynomials of degree 2 has dimension 3.)
    # Degree 2 is the lowest degree that allows for combination of multiple modes.
    # (A polynomial of degree 2 can be created either by P1(x)*P1(y) or by P0(x)*P2(y). For degree 0 you only have P0(x)*P0(y) and for degree 1 you only have P0(x)*P1(y).)
    # Order 4 is the smallest order that allows for a TT-rank larger than 3.
    order = len(_univariateDegrees)
    dimensions = [deg+1 for deg in _univariateDegrees]
    ranks = [dimensions[0]]
    blocks = [[block[0,l,l] for l in range(dimensions[0]) if l <= _maxTotalDegree]]
    for m in range(1, order-1):
        # blocks.append([block[l,e,r] for l in range(slices[m]) for e in range(dimensions[m]) for r in range(slices[m+1]) if e+l <= _maxTotalDegree])
        blocks.append([block[k,l,k+l] for k in range(ranks[-1]) for l in range(dimensions[m]) if k+l <= _maxTotalDegree])
        ranks.append(min(ranks[-1]-1 + dimensions[m]-1, _maxTotalDegree)+1)
    blocks.append([block[k,l,0] for k in range(ranks[-1]) for l in range(dimensions[-1]) if k+l <= _maxTotalDegree])
    return BlockSparseTT.random(dimensions, ranks, blocks)


def random_polynomial_v2(_univariateDegrees, _maxTotalDegree):
    order = len(_univariateDegrees)
    dimensions = [deg+1 for deg in _univariateDegrees]
    maxTheoreticalDegrees = np.minimum(np.cumsum(_univariateDegrees[:-1]), np.cumsum(_univariateDegrees[1:][::-1])[::-1])
    degrees = np.minimum(maxTheoreticalDegrees, _maxTotalDegree)  # what are the maximum possible degrees in each core
    slices = [1] + (degrees+1).tolist() + [1]
    ranks = slices[1:-1]  #TODO: only works because each block has size 1x1x1
    blocks = []
    for m in range(order):
        blocks.append([block[l,e,r] for l in range(slices[m]) for e in range(dimensions[m]) for r in range(slices[m+1]) if e <= abs(l-r)])
    return BlockSparseTT.random(dimensions, ranks, blocks)


def random_homogenous_polynomial(_univariateDegrees, _totalDegree, _blockSize=1):
    # Assume that _totalDegree <= _univariateDegrees. Then the necessary degree _totalDegree can be achieved by one component alone.
    # Moreover, not all polynomials of the given _totalDegree would be representable otherwise (notably x[k]**_totalDegree).
    # Using this assumption simplifies the block structure.
    _univariateDegrees = np.asarray(_univariateDegrees, dtype=int)
    assert isinstance(_totalDegree, int) and _totalDegree >= 0
    assert _univariateDegrees.ndim == 1 and np.all(_univariateDegrees >= _totalDegree)
    assert _blockSize == 1
    order = len(_univariateDegrees)
    dimensions = _univariateDegrees+1
    ranks = [_totalDegree+1]*(order-1)  #TODO: only works for _blockSize 1
    blocks = [[block[0,l,l] for l in range(_totalDegree+1)]]  # _totalDegree <= _univariateDegrees[0]
    for m in range(1, order-1):
        blocks.append([block[k,l,k+l] for k in range(_totalDegree+1) for l in range(_totalDegree+1-k)])  # k+l <= _totalDegree <--> l < _totalDegree+1-k
    blocks.append([block[k,_totalDegree-k,0] for k in range(_totalDegree+1)])  # k+l == _totalDegree <--> l == _totalDegree-k
    return BlockSparseTT.random(dimensions, ranks, blocks)


def random_homogenous_polynomial_v2(_univariateDegrees, _totalDegree, _maxGroupSize):
    # Assume that _totalDegree <= _univariateDegrees. Then the necessary degree _totalDegree can be achieved by one component alone.
    # Moreover, not all polynomials of the given _totalDegree would be representable otherwise (notably x[k]**_totalDegree).
    # Using this assumption simplifies the block structure.
    #
    # Die Intuition hinter einer Komponente C(l,m,l+m) ist, dass Gruppe l unter dem Einfluss von m auf Gruppe l+m abgebildet wird.
    # Die Größe der Gruppe l+m hängt dabei von der Größe der Gruppen l und m ab!
    # Bezeichne mit space(l,k) den Raum der von der Gruppe l in der k-ten Komponente des TTs auf gespannt wird und mit size(l,k) dessen Dimension.
    # Bezeichne außerdem mit poly(m) den Raum der vom m-ten Basispolynom aufgespannt wird. (Nimm an, dass deg(poly(m)) = m.)
    # Das ist die maximale Anzahl unterschiedlicher Polynome in Gruppe r der (k+1)-ten Komponente beschränkt duch
    #     size(r,k+1) = dim(space(r,k+1)) <= dim(sum(space(l,k)*poly(r-l) for l in range(r+1))) = sum(size(l,k) for l in range(r+1)) = np.sum(size(:r+1,k)).
    #
    # Wir wollen nun eine Formel für size() herleiten und verwenden dafür, dass _maxGroupSize für all k gleich ist.
    # Wir definieren size(r,k+1) = min(maxSize(r,k+1), _maxGroupSize) rekursiv mit maxSize(r,k+1) = np.sum(size(:r+1,k))
    # und definiere außerdem MaxSize(r,k+1) = np.sum(MaxSize(:r+1,k)).
    # Falls np.all(size(:r+1,k) < _maxGroupSize), dann gilt size(:r+1,k) = maxSize(:r+1,k) = MaxSize(:r,k+1) und folglich maxSize(r,k+1) = MaxSize(r,k+1) und
    #     size(r,k+1) = min(MaxSize(r,k+1), _maxGroupSize).
    # Falls jedoch np.any(size(:r+1,k) >= _maxGroupSize), dann folgen MaxSize(r,k+1) >= maxSize(r,k+1) = np.sum(size(:r+1,k)) > _maxGroupSize und
    #     size(r,k+1) = min(maxSize(r,k+1), _maxGroupSize) = _maxGroupSize = min(MaxSize(r,k+1), _maxGroupSize).
    # Insgesamt gilt also size(r,k) = min(MaxSize(r,k), _maxGroupSize) für alle r,k.
    #
    # Es bleibt nur noch eine Formel für MaxSize(r,k) zu finden.
    # Da MaxSize(r+1,k+1) = np.sum(MaxSize(:r+2,k)) = MaxSize(r,k+1) + MaxSize(r+1,k) folg aus Pascals Formel
    #     MaxSize(r,k) = comb(k+r,k) .
    # (Beachte, dass MaxSize(r+1,k+1) = comb(k+r+2,k+1) = comb(k+r+1,k) + comb(k+r+1,k+1) = MaxSize(r+1,k) + MaxSize(r,k+1).)
    #
    # Zuletzt beachte, dass sich gleiche Einschränkungen für die Gruppengröße auch von rechts nach links berechnen lassen.
    # Von rechts aus gezählt (angefangen bei 0!) befinden wir uns dann in der Komponente order-k-1.
    # Die linken Gruppen dieser Komponente sind die rechten der Komponente mk = order-k-2.
    # Von links aus gezählt haben wir bisher ein polynom von Grad r. Um ein Polynom von Grad _totalDegree zu erhalten 
    # muss also der Polynomgrad von rechts aus gezählt mr = _totalDegree-r sein.
    # In der Tat gilt also
    #     size(r,k) = min(comb(k+r,k), comb(mk+mr, mk), _maxGroupSize).
    _univariateDegrees = np.asarray(_univariateDegrees, dtype=int)
    assert isinstance(_totalDegree, int) and _totalDegree >= 0
    assert _univariateDegrees.ndim == 1 and np.all(_univariateDegrees >= _totalDegree)
    order = len(_univariateDegrees)

    def MaxSize(r,k):
        mr, mk = _totalDegree-r, order-k-2
        return min(comb(k+r,k), comb(mk+mr, mk), _maxGroupSize)

    dimensions = _univariateDegrees+1
    blocks = [[block[0,l,l] for l in range(_totalDegree+1)]]  # _totalDegree <= _univariateDegrees[0]
    ranks = []
    for k in range(1, order-1):
        mblocks = []
        leftSizes = [MaxSize(l,k-1) for l in range(_totalDegree+1)]
        leftSlices = np.cumsum([0] + leftSizes).tolist()
        rightSizes = [MaxSize(r,k) for r in range(_totalDegree+1)]
        rightSlices = np.cumsum([0] + rightSizes).tolist()
        for l in range(_totalDegree+1):
            for r in range(l, _totalDegree+1):  # If a polynomial of degree l is multiplied with another polynomial the degree must be at least l.
                m = r-l  # 0 <= m <= _totalDegree-l <= _totalDegree <= _univariateDegrees[m]
                mblocks.append(block[leftSlices[l]:leftSlices[l+1], m, rightSlices[r]:rightSlices[r+1]])
        ranks.append(leftSlices[-1])
        blocks.append(mblocks)
    ranks.append(_totalDegree+1)
    blocks.append([block[l,_totalDegree-l,0] for l in range(_totalDegree+1)])  # l+m == _totalDegree <--> m == _totalDegree-l
    return BlockSparseTT.random(dimensions, ranks, blocks)


def random_homogenous_polynomial_sum(_univariateDegrees, _totalDegree, _maxGroupSize):
    _univariateDegrees = np.asarray(_univariateDegrees, dtype=int)
    assert isinstance(_totalDegree, int) and _totalDegree >= 0
    assert _univariateDegrees.ndim == 1 and np.all(_univariateDegrees >= _totalDegree)
    order = len(_univariateDegrees)


    if isinstance(_maxGroupSize, int):
        _maxGroupSize = [_maxGroupSize]*len(_univariateDegrees)   

    def MaxSize(r,k):
        mr, mk = _totalDegree-r, order-k-1
        return min(comb(k+r,k), comb(mk+mr, mk), _maxGroupSize[k])

    dimensions = _univariateDegrees+1
    blocks = [[block[0,l,l] for l in range(_totalDegree+1)]]  # _totalDegree <= _univariateDegrees[0]
    ranks = []
    for k in range(1, order):
        mblocks = []
        leftSizes = [MaxSize(l,k-1) for l in range(_totalDegree+1)]
        leftSlices = np.cumsum([0] + leftSizes).tolist()
        rightSizes = [MaxSize(r,k) for r in range(_totalDegree+1)]
        rightSlices = np.cumsum([0] + rightSizes).tolist()
        for l in range(_totalDegree+1):
            for r in range(l, _totalDegree+1):  # If a polynomial of degree l is multiplied with another polynomial the degree must be at least l.
                m = r-l  # 0 <= m <= _totalDegree-l <= _totalDegree <= _univariateDegrees[m]
                mblocks.append(block[leftSlices[l]:leftSlices[l+1], m, rightSlices[r]:rightSlices[r+1]])
        ranks.append(leftSlices[-1])
        blocks.append(mblocks)
    #ranks.append(_totalDegree+1)
    #blocks.append([block[l,d-l,d] for d in range(_totalDegree+1) for l in range(d+1)])  # l+m == d <--> m == d-l
    ranks.append(_totalDegree+1)
    blocks.append([block[d,d,0] for d in range(_totalDegree+1)])
    return BlockSparseTT.random(dimensions.tolist()+[_totalDegree+1], ranks, blocks)

def random_homogenous_polynomial_sum_system(_univariateDegrees, _interactionranges, _totalDegree, _maxGroupSize,_selectionMatrix):
    _univariateDegrees = np.asarray(_univariateDegrees, dtype=int)
    assert isinstance(_totalDegree, int) and _totalDegree >= 0
    assert _univariateDegrees.ndim == 1 and np.all(_univariateDegrees >= _totalDegree)
    assert len(_univariateDegrees) == len(_interactionranges)
    assert isinstance(_interactionranges,list)
    order = len(_univariateDegrees)
    
    
    

    def MaxSize(r,k):
        mr, mk = _totalDegree-r, order-k-1
        return min(comb(k+r,k), comb(mk+mr, mk), _maxGroupSize)

    dimensions = _univariateDegrees+1
    numberOfEquations = len(dimensions)

    blocks = [[block[0,l,0:_interactionranges[0],l] for l in range(_totalDegree+1)]]  # _totalDegree <= _univariateDegrees[0]
    ranks = []
    for k in range(1, order):
        mblocks = []
        leftSizes = [MaxSize(l,k-1) for l in range(_totalDegree+1)]
        leftSlices = np.cumsum([0] + leftSizes).tolist()
        rightSizes = [MaxSize(r,k) for r in range(_totalDegree+1)]
        rightSlices = np.cumsum([0] + rightSizes).tolist()
        for l in range(_totalDegree+1):
            for r in range(l, _totalDegree+1):  # If a polynomial of degree l is multiplied with another polynomial the degree must be at least l.
                m = r-l  # 0 <= m <= _totalDegree-l <= _totalDegree <= _univariateDegrees[m]
                mblocks.append(block[leftSlices[l]:leftSlices[l+1], m, 0:_interactionranges[k], rightSlices[r]:rightSlices[r+1]])
        ranks.append(leftSlices[-1])
        blocks.append(mblocks)
    #ranks.append(_totalDegree+1)
    #blocks.append([block[l,d-l,0:_interactionranges[-1],d] for d in range(_totalDegree+1) for l in range(d+1)])  # l+m == d <--> m == d-l
    ranks.append(_totalDegree+1)
    blocks.append([block[d,_totalDegree-d,0,0] for d in range(_totalDegree+1)])
    return BlockSparseTTSystem.random(dimensions.tolist()+[_totalDegree+1], ranks,_interactionranges +[1],  blocks, numberOfEquations,_selectionMatrix)

def zeros_homogenous_polynomial_sum_system(_univariateDegrees, _interactionranges, _totalDegree, _maxGroupSize,_selectionMatrix):
    _univariateDegrees = np.asarray(_univariateDegrees, dtype=int)
    assert isinstance(_totalDegree, int) and _totalDegree >= 0
    assert _univariateDegrees.ndim == 1 and np.all(_univariateDegrees >= _totalDegree)
    assert len(_univariateDegrees) == len(_interactionranges)
    assert isinstance(_interactionranges,list)
    order = len(_univariateDegrees)

    def MaxSize(r,k):
        mr, mk = _totalDegree-r, order-k-2
        return min(comb(k+r,k), comb(mk+mr, mk), _maxGroupSize)

    dimensions = _univariateDegrees+1
    numberOfEquations = len(dimensions)

    blocks = [[block[0,l,0:_interactionranges[0],l] for l in range(_totalDegree+1)]]  # _totalDegree <= _univariateDegrees[0]
    ranks = []
    for k in range(1, order-1):
        mblocks = []
        leftSizes = [MaxSize(l,k-1) for l in range(_totalDegree+1)]
        leftSlices = np.cumsum([0] + leftSizes).tolist()
        rightSizes = [MaxSize(r,k) for r in range(_totalDegree+1)]
        rightSlices = np.cumsum([0] + rightSizes).tolist()
        for l in range(_totalDegree+1):
            for r in range(l, _totalDegree+1):  # If a polynomial of degree l is multiplied with another polynomial the degree must be at least l.
                m = r-l  # 0 <= m <= _totalDegree-l <= _totalDegree <= _univariateDegrees[m]
                mblocks.append(block[leftSlices[l]:leftSlices[l+1], m, 0:_interactionranges[k], rightSlices[r]:rightSlices[r+1]])
        ranks.append(leftSlices[-1])
        blocks.append(mblocks)
    ranks.append(_totalDegree+1)
    blocks.append([block[l,d-l,0:_interactionranges[-1],d] for d in range(_totalDegree+1) for l in range(d+1)])  # l+m == d <--> m == d-l
    ranks.append(_totalDegree+1)
    blocks.append([block[d,_totalDegree-d,0,0] for d in range(_totalDegree+1)])
    return BlockSparseTTSystem.zeros(dimensions.tolist()+[_totalDegree+1], ranks,_interactionranges +[1],  blocks, numberOfEquations,_selectionMatrix)





def max_group_size(_order, _degree):
    def MaxSize(r, k):
        mr, mk = _degree-r, _order-k-2
        return min(comb(k+r,k), comb(mk+mr, mk))
    # The maximal group sizes for core 0 and order-1 are 1.
    return max(max(max(MaxSize(deg, pos-1) for deg in range(_degree+1)) for pos in range(1, _order-1)), 1)


def monomial_measures(_points, _degree):
    N,M = _points.shape
    ret = _points.T[...,None]**np.arange(_degree+1)[None,None]
    assert ret.shape == (M, N, _degree+1)
    return ret


def legendre_measures(_points, _degree,_a=-1,_b=1):
    assert _a < _b
    N,M = _points.shape # sample x order
    factors = np.sqrt(2*np.arange(_degree+1)+1)
    ret =  legval(2/(_b-_a)*(_points-_a)-1, np.diag(factors)).T
    assert ret.shape == (M, N, _degree+1)
    return ret

def legendre_measures_grad(_points, _degree,_a=-1,_b=1):
    assert _a < _b
    N,M = _points.shape
    factors = np.sqrt(2*np.arange(_degree+1)+1)
    ret = legval(2/(_b-_a)*(_points-_a)-1, np.diag(factors)).T
    assert ret.shape == (M, N, _degree+1)
    ret_der = legval(2/(_b-_a)*(_points-_a)-1, 2/(_b-_a)*legder(np.diag(factors))).T
    grad = []
    for k in range(M):
        ret_tmp = ret.copy()
        ret_tmp[k,:,:] = ret_der[k,:,:]
        grad.append(ret_tmp)
    return grad


def hermite_measures(_points, _degree):
    N,M = _points.shape
    factors = 1/np.sqrt(np.sqrt(2*np.pi)*np.array([factorial(l) for l in range(_degree+1)]))
    ret = hermeval(_points, np.diag(factors)).T
    assert ret.shape == (M, N, _degree+1)
    return ret


# def random_nearest_neighbor_polynomial(_univariateDegrees, _nnranks):
#     dimensions = [dim+1 for dim in _univariateDegrees]
#     nnslice = np.concatenate([0], np.cumsum(np.concatenate([1], _nnranks)))
#     nnslice = [slice(s1, s2) for s1,s2 in zip(nnslice[:-1], nnslice[1:])]
#     dimslice = [slice(0, dim) for dim in dimensions]

#     ranks = []
#     blocks = []
#     currentMaxNeighbors = 0
#     maxNeighbors = len(_nnranks)
#     for m in range(len(_dimensions)-1):
#         blocks_m = []
#         blocks_m.append(block[nnslice[0], 0, nnslice[0]])
#         for n in range(min(currenMaxNeighbors, maxNeighbors-1)):
#             blocks_m.append(block[nnslice[n], dimslice[m], nnslice[n+1]])
#         if currenMaxNeighbors == maxNeighbors:
#             blocks_m.append(block[nnslice[-1], 0, nnslice[-1]])
#         ranks.append(max(blk[2].stop for blk in blocks_m))
#         blocks.append(blocks_m)
#         currenMaxNeighbors = min(currenMaxNeighbors+1, len(_nnranks))
#     blocks.append([block[nnslice[-1],0,0], block[nnslice[-2],:,0]])
#     return BlockSparseTT.random(dimensions, ranks, blocks)


def random_full(_univariateDegrees, _ranks):
    """
    Create a randomly initialized TT with the given rank.

    Note that this TT  will not have sparse blocks!
    """
    order = len(_univariateDegrees)
    dimensions = [dim+1 for dim in _univariateDegrees]
    maxTheoreticalRanks = np.minimum(np.cumprod(dimensions[:-1]), np.cumprod(dimensions[1:][::-1])[::-1])
    ranks = [1] + np.minimum(maxTheoreticalRanks, _ranks).tolist() + [1]
    blocks = [[block[0:ranks[m],0:dimensions[m],0:ranks[m+1]]] for m in range(order)]
    return BlockSparseTT.random(dimensions, ranks[1:-1], blocks)


def random_full_system(_univariateDegrees, _interactionranges, _ranks):
    """
    Create a randomly initialized TT with the given rank.

    Note that this TT  will not have sparse blocks!
    """
    order = len(_univariateDegrees)
    dimensions = [dim+1 for dim in _univariateDegrees]
    maxTheoreticalRanks = np.minimum(np.cumprod(dimensions[:-1]), np.cumprod(dimensions[1:][::-1])[::-1])
    ranks = [1] + np.minimum(maxTheoreticalRanks, _ranks).tolist() + [1]
    blocks = [[block[0:ranks[m],0:dimensions[m],0:_interactionranges[m],0:ranks[m+1]]] for m in range(order)]
    return BlockSparseTTSystem.random(dimensions, ranks[1:-1],_interactionranges, blocks,order)




def recover_ml(_measures, _values, _degrees, _maxGroupSize, _maxIter=10, _maxSweeps=100, _targetResidual=1e-12, _verbosity=0):
    if isinstance(_degrees, int):
        _degrees = list(range(_degrees+1))
    maxDegree = max(_degrees)
    order, numSamples, dimension = _measures.shape
    assert (numSamples,) == _values.shape and  dimension == maxDegree+1, f"NOT ({(numSamples,)} == {_values.shape} and {dimension} == {maxDegree+1})"

    def residual(_bstts):
        pred = sum(bstt.evaluate(_measures) for bstt in _bstts)
        return np.linalg.norm(pred -  _values) / np.linalg.norm(_values)

    bstts = [random_homogenous_polynomial_v2([maxDegree]*order, deg, _maxGroupSize) for deg in _degrees]
    for bstt in bstts:
        bstt.assume_corePosition(order-1)
        while bstt.corePosition > 0: bstt.move_core('left')
        bstt.components[0] *= 1e-3/np.linalg.norm(bstt.components[0])
    if _verbosity >= 1: print("="*80)
    res = np.inf
    for itr in range(_maxIter):
        if _verbosity >= 1: print(f"Iteration: {itr}")
        for lvl in range(len(bstts)):
            lvl_values = _values - sum(bstt.evaluate(_measures) for bstt in bstts[:lvl]+bstts[lvl+1:])
            solver = ALS(bstts[lvl], _measures, lvl_values, _verbosity=_verbosity-1)
            solver.maxSweeps = _maxSweeps
            solver.targetResidual = _targetResidual
            solver.run()
            bstts[lvl] = solver.bstt
        old_res, res = res, residual(bstts)
        if _verbosity >= 1: print(f"Residual: {res:.2e}")
        if old_res < res or res < _targetResidual: break
        if _verbosity >= 1 and itr < _maxIter-1: print("-"*80)
    # print("="*80)
    return bstts


def L2innerLegendre(c1, c2):
    i = legint(legmul(c1, c2))
    return (legval(1, i) - legval(-1, i))

def HkinnerLegendre(k):
    assert isinstance(k, int) and k >= 0
    def inner(c1, c2,_a,_b):
        ret = L2innerLegendre(c1, c2)
        for j in range(k):
            c1 = 2/(_b-_a)*legder(c1)
            c2 = 2/(_b-_a)*legder(c2)
            ret += L2innerLegendre(c1, c2)
        return ret
    return inner

def Gramian(d, inner,_a=-1,_b=1):
    matrix = np.empty((d,d))
    e = lambda k: np.sqrt(2*k+1)*np.eye(1,d,k)[0]
    for i in range(d):
        ei = e(i)
        for j in range(i+1):
            ej = e(j)
            matrix[i,j] = matrix[j,i] = inner(ei,ej,_a,_b)
    return matrix
