"""Portable gameplay RNG; identical integer operations in Python and CUDA.

Level generation retains its independent Python RNG. This stream belongs to one
game and is saved in snapshots; it is never supplied to a playing policy.
"""


def next_u32(state: int) -> int:
    state ^= (state << 13) & 0xFFFFFFFF
    state ^= state >> 17
    state ^= (state << 5) & 0xFFFFFFFF
    return state & 0xFFFFFFFF


def initial_state(seed: int) -> int:
    return (seed ^ 0x9E3779B9) & 0xFFFFFFFF or 1
