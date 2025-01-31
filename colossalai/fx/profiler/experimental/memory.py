# for PyTorch 1.11 compatibility uses
import torch
from torch.fx import Node, GraphModule
from typing import Union, Dict, List, Tuple

__all__ = ["calculate_fwd_in", "calculate_fwd_tmp", "calculate_fwd_out"]


def calculate_fwd_in(n: Node) -> bool:
    """A helper function to calculate `fwd_in`

    Args:
        n (Node): a node from the graph

    Returns:
        save_fwd_in (bool): the result of `save_fwd_in`
    """
    return n.meta['save_fwd_in']


def calculate_fwd_tmp(n: Node) -> int:
    """A helper function to calculate `fwd_tmp`

    Args:
        n (Node): a node from the graph

    Returns:
        fwd_tmp (int): the result of `fwd_tmp`
    """
    return n.meta["fwd_mem_tmp"]


def calculate_fwd_out(n: Node) -> int:
    """A helper function to calculate `fwd_out`

    Args:
        n (Node): a node from the graph

    Returns:
        fwd_out (int): the result of `fwd_out`
    """
    return n.meta['fwd_mem_out']
