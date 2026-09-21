"""Optional batched CUDA simulation; importing ordinary gameplay needs no CUDA."""

from .backend import CapacityError, CudaBatch

__all__ = ["CudaBatch", "CapacityError"]
