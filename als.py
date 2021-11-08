#NOTE: This implementation is not meant to be memory efficient or fast but rather to test the approximation capabilities of the proposed model class.
import numpy as np
from bstt import Block, BlockSparseTensor


class ALS(object):
    def __init__(self, _bstt, _measurements, _values, _localGramians=None, _verbosity=0):
        self.bstt = _bstt
        assert isinstance(_measurements, np.ndarray) and isinstance(_values, np.ndarray)
        assert len(_measurements) == self.bstt.order
        assert all(compMeas.shape == (len(_values), dim) for compMeas, dim in zip(_measurements, self.bstt.dimensions))
        self.measurements = _measurements
        self.values = _values
        self.verbosity = _verbosity
        self.maxSweeps = 100
        self.targetResidual = 1e-8
        self.minDecrease = 1e-4

        if (not _localGramians): 
            self.localGramians = [np.eye(d) for d in self.bstt.dimensions]
        else:
            assert isinstance(_localGramians,list) and len(_localGramians) == self.bstt.order
            for i in range(len(_localGramians)):
                lG = _localGramians[i]
                assert isinstance(lG, np.ndarray) and lG.shape == (self.bstt.dimensions[i],self.bstt.dimensions[i])
                assert np.all(np.linalg.eigvals(lG) >= 0) and np.allclose(lG, lG.T, rtol=1e-14, atol=1e-14)
            self.localGramians =_localGramians
    
        self.leftStack = [np.ones((len(self.values),1))] + [None]*(self.bstt.order-1)
        self.rightStack = [np.ones((len(self.values),1))]
        self.leftGramianStack = [np.ones([1,1])]  + [None]*(self.bstt.order-1)
        self.rightGramianStack = [np.ones([1,1])]
        self.bstt.assume_corePosition(self.bstt.order-1)
        while self.bstt.corePosition > 0:
            self.move_core('left')

    def move_core(self, _direction):
        assert len(self.leftStack) + len(self.rightStack) == self.bstt.order+1
        assert len(self.leftGramianStack) + len(self.rightGramianStack) == self.bstt.order+1
        valid_stacks = all(entry is not None for entry in self.leftStack + self.rightStack)
        if self.verbosity >= 2 and valid_stacks:
            pre_res = self.residual()
        self.bstt.move_core(_direction)
        if _direction == 'left':
            self.leftStack.pop()
            self.leftGramianStack.pop()
            self.rightStack.append(np.einsum('ler, ne, nr -> nl', self.bstt.components[self.bstt.corePosition+1], self.measurements[self.bstt.corePosition+1], self.rightStack[-1]))
            self.rightGramianStack.append(np.einsum('ijk, lmn, jm,kn -> il', self.bstt.components[self.bstt.corePosition+1],  self.bstt.components[self.bstt.corePosition+1], self.localGramians[self.bstt.corePosition+1], self.rightGramianStack[-1]))
            if self.verbosity >= 2:
                if valid_stacks:
                    print(f"move_core {self.bstt.corePosition+1} --> {self.bstt.corePosition}.  (residual: {pre_res:.2e} --> {self.residual():.2e})")
                else:
                    print(f"move_core {self.bstt.corePosition+1} --> {self.bstt.corePosition}.")
        elif _direction == 'right':
            self.rightStack.pop()
            self.rightGramianStack.pop()
            self.leftStack.append(np.einsum('nl, ne, ler -> nr', self.leftStack[-1], self.measurements[self.bstt.corePosition-1], self.bstt.components[self.bstt.corePosition-1]))
            self.leftGramianStack.append(np.einsum('ijk, lmn, jm,il -> kn', self.bstt.components[self.bstt.corePosition-1],  self.bstt.components[self.bstt.corePosition-1], self.localGramians[self.bstt.corePosition-1], self.leftGramianStack[-1]))
            if self.verbosity >= 2:
                if valid_stacks:
                    print(f"move_core {self.bstt.corePosition-1} --> {self.bstt.corePosition}.  (residual: {pre_res:.2e} --> {self.residual():.2e})")
                else:
                    print(f"move_core {self.bstt.corePosition-1} --> {self.bstt.corePosition}.")
        else:
            raise ValueError(f"Unknown _direction. Expected 'left' or 'right' but got '{_direction}'")

    def residual(self):
        core = self.bstt.components[self.bstt.corePosition]
        L = self.leftStack[-1]
        E = self.measurements[self.bstt.corePosition]
        R = self.rightStack[-1]
        pred = np.einsum('ler,nl,ne,nr -> n', core, L, E, R)
        return np.linalg.norm(pred -  self.values) / np.linalg.norm(self.values)

    def microstep(self):
        if self.verbosity >= 2:
            pre_res = self.residual()

        core = self.bstt.components[self.bstt.corePosition]
        L = self.leftStack[-1]
        E = self.measurements[self.bstt.corePosition]
        R = self.rightStack[-1]
        coreBlocks = self.bstt.blocks[self.bstt.corePosition]
        N = len(self.values)

        Op_blocks = []
        for block in coreBlocks:
            op = np.einsum('nl,ne,nr -> nler', L[:, block[0]], E[:, block[1]], R[:, block[2]])
            Op_blocks.append(op.reshape(N,-1))
        Op = np.concatenate(Op_blocks, axis=1)
        # Res = np.linalg.solve(Op.T @ Op, Op.T @ self.values)
        Res, *_ = np.linalg.lstsq(Op, self.values, rcond=None)  # When Op.T@Op is singular (less samples then dofs in this component) then lstsq returns the minimal norm solution.
        core[...] = BlockSparseTensor(Res, coreBlocks, core.shape).toarray()

        if self.verbosity >= 2:
            print(f"microstep.  (residual: {pre_res:.2e} --> {self.residual():.2e})")

    def run(self):
        prev_residual = self.residual()
        if self.verbosity >= 1: print(f"Initial residuum: {prev_residual:.2e}")
        for sweep in range(self.maxSweeps):
            while self.bstt.corePosition < self.bstt.order-1:
                self.microstep()
                self.move_core('right')
            while self.bstt.corePosition > 0:
                self.microstep()
                self.move_core('left')

            residual = self.residual()
            if self.verbosity >= 1: print(f"[{sweep}] Residuum: {residual:.2e}")

            if residual < self.targetResidual:
                if self.verbosity >= 1:
                    print(f"Terminating (targetResidual reached)")
                    print(f"Final residuum: {self.residual():.2e}")
                return

            if residual > prev_residual:
                if self.verbosity >= 1:
                    print(f"Terminating (residual increases)")
                    print(f"Final residuum: {self.residual():.2e}")
                return

            if (prev_residual - residual) < self.minDecrease*residual:
                if self.verbosity >= 1:
                    print(f"Terminating (minDecrease reached)")
                    print(f"Final residuum: {self.residual():.2e}")
                return

            prev_residual = residual

        if self.verbosity >= 1: print(f"Terminating (maxSweeps reached)")
        if self.verbosity >= 1: print(f"Final residuum: {self.residual():.2e}")
