import torch
from typing import List
from torch.fx import symbolic_trace
from torch.fx.node import Node
from colossalai.fx.passes.split_module import split_module
from colossalai.tensor.shape_consistency import ShapeConsistencyManager
from colossalai.device.device_mesh import DeviceMesh
from colossalai.tensor.sharding_spec import ShardingSpec, _DimSpec
import builtins
import operator
from copy import deepcopy


def apply(*args, **kwargs):
    shape_consistency_manager = ShapeConsistencyManager()
    return shape_consistency_manager.apply(*args, **kwargs)


def solution_annotatation_pass(gm: torch.fx.GraphModule, solution: List[int], device_mesh):
    mod_graph = gm.graph
    nodes = tuple(mod_graph.nodes)

    # the dict to get origin sharding spec of node
    origin_node_sharding_spec_dict = {}
    for node_index, (node, strategy_index) in enumerate(zip(nodes, solution)):
        strategies_vector = node.strategies_vector
        setattr(node, 'best_strategy', strategies_vector[strategy_index])
        setattr(node, 'sharding_spec', strategies_vector[strategy_index].get_sharding_spec_by_name(str(node)))
        origin_node_sharding_spec_dict[node_index] = strategies_vector[strategy_index].get_sharding_spec_by_name(
            str(node))

    # apply the sharding spec of parameters
    for node in nodes:
        if node.op == 'call_module':
            target_module = node.graph.owning_module.get_submodule(node.target)
            for name, param in target_module.named_parameters():
                origin_sharding_spec = ShardingSpec(device_mesh, param.shape, {})
                setattr(param, 'sharding_spec', origin_sharding_spec)
                target_weight_sharding_spec = node.best_strategy.get_sharding_spec_by_name(name)
                apply(param, target_weight_sharding_spec)

    # the dict to get input sharding specs of user node
    sharding_spec_convert_dict = {}
    for index, node in enumerate(nodes):
        target_sharding_specs = []
        if node.name == 'bn1':
            print(node.strategies_vector.successor_nodes)
            assert False
        for user_node in node.strategies_vector.successor_nodes:
            # node_index = user_node.strategies_vector.predecessor_nodes.index(node)
            # target_sharding_spec = user_node.best_strategy.input_shardings[node_index]
            target_sharding_spec = user_node.best_strategy.get_sharding_spec_by_name(str(node.name))
            target_sharding_specs.append(target_sharding_spec)
        sharding_spec_convert_dict[index] = target_sharding_specs

    # add above dicts into graph
    for node in nodes:
        if node.op != 'placeholder':
            with mod_graph.inserting_before(node):
                input_specs_node = mod_graph.create_node('placeholder', target='sharding_spec_convert_dict')
                origin_specs_node = mod_graph.create_node('placeholder', target='origin_node_sharding_spec_dict')
            break

    return sharding_spec_convert_dict, origin_node_sharding_spec_dict


def shape_consistency_pass(gm: torch.fx.GraphModule):
    mod_graph = gm.graph
    nodes = tuple(mod_graph.nodes)
    input_dict_node = None
    origin_dict_node = None

    # mapping the node into the origin graph index
    node_to_index_dict = {}
    index = 0
    for node in nodes:
        if node.target == 'sharding_spec_convert_dict':
            input_dict_node = node
            continue
        if node.target == 'origin_node_sharding_spec_dict':
            origin_dict_node = node
            continue
        if not hasattr(node, 'best_strategy'):
            continue
        node_to_index_dict[node] = index
        index += 1
    assert input_dict_node is not None

    # add shape consistency apply function into graph
    for node in nodes:
        if not hasattr(node, 'best_strategy'):
            continue
        with mod_graph.inserting_after(node):
            origin_spec_node = mod_graph.create_node('call_function',
                                                     operator.getitem,
                                                     args=(origin_dict_node, node_to_index_dict[node]))
        with mod_graph.inserting_after(origin_spec_node):
            set_sharding_spec_node = mod_graph.create_node('call_function',
                                                           builtins.setattr,
                                                           args=(node, 'sharding_spec', origin_spec_node))

        for user_node in node.strategies_vector.successor_nodes:
            node_index = user_node.strategies_vector.predecessor_nodes.index(node)
            with mod_graph.inserting_before(user_node):
                input_specs_node = mod_graph.create_node('call_function',
                                                         operator.getitem,
                                                         args=(input_dict_node, node_to_index_dict[node]))
            with mod_graph.inserting_before(user_node):
                sharding_spec_node = mod_graph.create_node('call_function',
                                                           operator.getitem,
                                                           args=(input_specs_node, node_index))
            with mod_graph.inserting_before(user_node):
                shape_consistency_node = mod_graph.create_node('call_function', apply, args=(node, sharding_spec_node))

    return gm
