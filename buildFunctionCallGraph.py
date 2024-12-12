import json
import warnings

import networkx as nx
from typing import List


def build_function_call_graph(json_path: str) -> nx.DiGraph:
    """
    从 JSON 文件构建函数调用图
    :param json_path: JSON 文件路径
    :return: NetworkX DiGraph 对象，表示函数调用图
    """
    # 加载 JSON 文件
    with open(json_path, 'r') as f:
        call_data = json.load(f)

    # 初始化有向图
    call_graph = nx.DiGraph()

    # 遍历 JSON 数据，添加节点和边
    for caller, callees in call_data.items():
        call_graph.add_node(caller)  # 添加调用者节点
        for callee in callees:
            call_graph.add_edge(caller, callee)  # 添加调用关系的边

    return call_graph


def preorder_traverse_with_networkx(graph: nx.DiGraph, start_node: str) -> List[str]:
    """
    使用 networkx 的深度优先搜索进行先序遍历，不包含起始节点
    :param graph: NetworkX DiGraph 对象，函数调用图
    :param start_node: 起始节点（函数名）
    :return: 遍历的节点列表
    """
    # 检查节点是否在图中
    if start_node not in graph:
        warnings.warn(f"Function {start_node} not found in the graph."
                      f"This might be because the member function is declared in the test fixture but not defined.")
        return []

    # 初始化结果列表
    result: List[str] = []

    # 使用 dfs_preorder_nodes 进行先序遍历
    first = True  # 用于跳过第一个节点
    for node in nx.dfs_preorder_nodes(graph, source=start_node):
        if first:  # 跳过第一个节点
            first = False
            continue
        result.append(node)

    return result


if __name__ == "__main__":
    # 定义 JSON 文件路径
    json_path: str = "/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test/call_graph_all.json"

    # 构建函数调用图
    call_graph: nx.DiGraph = build_function_call_graph(json_path)

    # 定义起始函数节点
    start_function: str = "/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test/decode_test_driver | DecodeFrame"

    # 先序遍历函数调用图
    result_list: List[str] = preorder_traverse_with_networkx(call_graph, start_function)

    # 输出结果
    print("Function call traversal result:")
    print(result_list)
