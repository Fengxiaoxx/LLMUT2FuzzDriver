import os.path

from utils import parse_test_case_source,extract_lines
from buildFunctionCallGraph import build_function_call_graph,preorder_traverse_with_networkx
import networkx as nx
import warnings
from typing import Dict, Any
import json

def process_var_class(var_class_list:list, method_definition:Dict[str,Any],call_graph: nx.Graph,class_infos:Dict):
    var_class_infos = []
    for var_class_id in var_class_list:
        var_class_info = class_infos.get(var_class_id)

        var_class_defnition_info = var_class_info.get("class_definition")
        var_class_defnition_file = var_class_defnition_info.get("file")
        var_class_defnition_start_line = var_class_defnition_info.get("start_line")
        var_class_defnition_end_line = var_class_defnition_info.get("end_line")

        var_class_defnition = extract_lines(var_class_defnition_file,var_class_defnition_start_line,var_class_defnition_end_line)

        cxx_method_list = var_class_info.get("cxx_method_list")

        cxx_target_function_called_in_var_class = set()
        cxxmethod_definition_in_var_class = set()
        cxx_type_ref_set_in_var_class = set()


        #分析成员函数
        for cxx_method in cxx_method_list:

            isSrcCode = cxx_method.get("isSrcCode")
            cxxmethod_id = cxx_method.get("cxxmethod_id")

            #取成员函数的信息
            cxxmethod_definition, cxx_target_calld_list, cxx_type_ref_list, cxxmethod_id = extract_function_info(
                cxxmethod_id, method_definition)
            #将成员函数中的信息存入
            if cxx_target_calld_list is not None:
                cxx_target_function_called_in_var_class.update(cxx_target_calld_list)

            if not isSrcCode:
                cxxmethod_definition_in_var_class.add(cxxmethod_definition)

            if cxx_type_ref_list is not None:
                cxx_type_ref_set_in_var_class.update(set(cxx_type_ref_list))


            #取成员函数所调用的辅助函数信息
            cxx_aux_method_list = preorder_traverse_with_networkx(call_graph,cxxmethod_id)


            for cxx_aux_method in cxx_aux_method_list:
                aux_method_definition, aux_target_called_list, aux_type_ref_list, _ =  extract_function_info(cxx_aux_method, method_definition)
                if aux_method_definition is not None and not isSrcCode:
                    cxxmethod_definition_in_var_class.add(aux_method_definition)
                if aux_target_called_list is not None:
                    cxx_target_function_called_in_var_class.update(set(aux_target_called_list))
                if aux_type_ref_list is not None:
                    cxx_type_ref_set_in_var_class.update(set(aux_type_ref_list))


        type_def_list_in_fixture = var_class_info.get("type_def_list_in_class")
        for type_ref in type_def_list_in_fixture:
            type_def_info = type_ref.get("type_def")
            type_def_file = type_def_info.get("file")
            type_def_start_line = type_def_info.get("start_line")
            type_def_end_line = type_def_info.get("end_line")
            type_def_file_content = extract_lines(type_def_file, type_def_start_line, type_def_end_line)
            cxx_type_ref_set_in_var_class.add(type_def_file_content)

            flag = type_ref.get("flag")
            if flag:
                underlying_type_def_info = type_ref.get("underlying_type")
                underlying_type_def_file = underlying_type_def_info.get("file")
                underlying_type_def_start_line = underlying_type_def_info.get("start_line")
                underlying_type_def_end_line = underlying_type_def_info.get("end_line")
                underlying_type_def_file_content = extract_lines(underlying_type_def_file,
                                                                 underlying_type_def_start_line,
                                                                 underlying_type_def_end_line)
                cxx_type_ref_set_in_var_class.add(underlying_type_def_file_content)

        var_class_info = {
            "var_class_defnition":var_class_defnition,
            "cxx_target_function_called_in_var_class":list(cxx_target_function_called_in_var_class),
            "cxxmethod_definition_in_var_class":list(cxxmethod_definition_in_var_class),
            "cxx_type_ref_set_in_var_class":list(cxx_type_ref_set_in_var_class)
        }

        var_class_infos.append(var_class_info)
    return var_class_infos



def extract_evalgen_info(
    test_case_id: str,
    evalgen_infos: Dict,
    testcase_to_evlgen: Dict,
    var_infos: Dict,
    call_graph: nx.Graph,
    class_infos: Dict,
    method_definition: Dict
):
    eval_id_list = testcase_to_evlgen.get(test_case_id)  # 给定测试用例，提取所对应的参数生成器id

    if eval_id_list is None:
        return None

    eval_info_list =[]

    for eval_id in eval_id_list:
        eval_info = evalgen_infos.get(eval_id)  # 取参数生成器信息
        eval_file = eval_info.get('file')
        eval_start_line = eval_info.get('start_line')
        eval_end_line = eval_info.get('end_line')

        aux_definition_in_eval_all = set()
        target_function_call_in_eval_all = set()
        type_ref_list_in_eval_all = []
        var_ref_set = set()
        class_ref_definition_set = set()

        # 提取函数定义
        evalgen_definition = extract_lines(eval_file, eval_start_line, eval_end_line)

        # 提取内部调用的目标函数
        target_function_call_in_eval = eval_info.get("target_function_call")
        if target_function_call_in_eval:
            target_function_call_in_eval_all.update(target_function_call_in_eval)

        # 获取辅助函数列表并提取信息
        aux_function_call_list = preorder_traverse_with_networkx(call_graph, eval_id)

        for aux_function_id in aux_function_call_list:
            function_definition, target_function_called, type_ref_list, _ = extract_function_info(
                aux_function_id, method_definition
            )

            if function_definition:
                aux_definition_in_eval_all.add(function_definition)
            if target_function_called:
                target_function_call_in_eval_all.update(target_function_called)
            if type_ref_list:
                for type_ref in type_ref_list:
                    if type_ref not in type_ref_list_in_eval_all:
                        type_ref_list_in_eval_all.append(type_ref)

        # 提取内部调用的变量信息
        vars_ref_id = eval_info.get("var_ref")
        if vars_ref_id:
            for var_ref_id in vars_ref_id:
                var_ref_info = var_infos.get(var_ref_id)  # 获取变量信息
                var_ref_definition_info = var_ref_info.get('var_definition')

                var_ref_file = var_ref_definition_info.get('file')
                var_ref_start_line = var_ref_definition_info.get('start_line')
                var_ref_end_line = var_ref_definition_info.get('end_line')

                # 提取参数生成器中的变量定义
                var_ref_definition = extract_lines(var_ref_file, var_ref_start_line, var_ref_end_line)
                var_ref_set.add(var_ref_definition)

                # 提取变量中引用的目标函数列表
                target_functions_call_in_var = var_ref_info.get("target_functions_call_in_var")
                if target_functions_call_in_var:
                    target_function_call_in_eval_all.update(target_functions_call_in_var)

                # 提取变量中的类型引用列表
                var_type_ref_list = var_ref_info.get("var_type_ref_list")
                if var_type_ref_list:
                    for type_ref in var_type_ref_list:
                        type_def_info = type_ref.get("type_def")
                        type_def_file = type_def_info.get("file")
                        type_def_start_line = type_def_info.get("start_line")
                        type_def_end_line = type_def_info.get("end_line")
                        type_def_file_content = extract_lines(type_def_file, type_def_start_line, type_def_end_line)
                        if type_def_file_content not in type_ref_list_in_eval_all:
                            type_ref_list_in_eval_all.append(type_def_file_content)

                        flag = type_ref.get("flag")
                        if flag:
                            underlying_type_def_info = type_ref.get("underlying_type")
                            underlying_type_def_file = underlying_type_def_info.get("file")
                            underlying_type_def_start_line = underlying_type_def_info.get("start_line")
                            underlying_type_def_end_line = underlying_type_def_info.get("end_line")
                            underlying_type_def_file_content = extract_lines(
                                underlying_type_def_file,
                                underlying_type_def_start_line,
                                underlying_type_def_end_line
                            )
                            if underlying_type_def_file_content not in type_ref_list_in_eval_all:
                                type_ref_list_in_eval_all.append(underlying_type_def_file_content)

                # 提取变量中引用的类
                var_aux_classes = var_ref_info.get("var_aux_classes")
                if var_aux_classes:
                    var_classes_info = process_var_class(var_aux_classes, method_definition, call_graph, class_infos)

                    for var_class_info in var_classes_info:
                        var_class_defnition = var_class_info.get("var_class_defnition")
                        class_ref_definition_set.add(var_class_defnition)

                        cxx_target_function_called_in_var_class = var_class_info.get(
                            "cxx_target_function_called_in_var_class"
                        )
                        target_function_call_in_eval_all.update(cxx_target_function_called_in_var_class)

                        cxxmethod_definition_in_var_class = var_class_info.get("cxxmethod_definition_in_var_class")
                        aux_definition_in_eval_all.update(cxxmethod_definition_in_var_class)

                        cxx_type_ref_set_in_var_class = var_class_info.get("cxx_type_ref_set_in_var_class")
                        for type_ref in cxx_type_ref_set_in_var_class:
                            if type_ref not in type_ref_list_in_eval_all:
                                type_ref_list_in_eval_all.append(type_ref)

                # 提取变量中引用的辅助函数列表
                aux_functions_call_in_var = var_ref_info.get("aux_functions_call_in_var")
                if aux_functions_call_in_var:
                    for aux_function in aux_functions_call_in_var:
                        function_definition_var_aux, target_function_called_var_aux, type_ref_list_var_aux, _ = extract_function_info(
                            aux_function, method_definition
                        )
                        if function_definition_var_aux:
                            aux_definition_in_eval_all.add(function_definition_var_aux)
                        if target_function_called_var_aux:
                            target_function_call_in_eval_all.update(target_function_called_var_aux)
                        if type_ref_list_var_aux:
                            for type_ref in type_ref_list_var_aux:
                                if type_ref not in type_ref_list_in_eval_all:
                                    type_ref_list_in_eval_all.append(type_ref)

        eval = {
            "file": os.path.basename(eval_file),
            "evalgen_definition": evalgen_definition,
            "aux_definition_in_eval_all": list(aux_definition_in_eval_all),
            "target_function_call_in_eval_all": list(target_function_call_in_eval_all),
            "var_ref_set": list(var_ref_set),
            "type_ref_set_in_eval_all": type_ref_list_in_eval_all,
            "class_ref_definition_set": list(class_ref_definition_set)
        }
        eval_info_list.append(eval)

    return eval_info_list


def approximate_match(aux_function: str, method_definition: dict):  #只有成员函数需要模糊匹配
    # 将 aux_function 按照 " & " 进行分割
    aux_parts = aux_function.split(" & ")

    # 遍历 method_definition 中的每一个 key 和对应的 value
    for key, value in method_definition.items():
        # 将 key 按照 " & " 进行分割
        key_parts = key.split(" & ")


        # 检查 aux_parts 和 key_parts 是否有共同的部分
        if set(aux_parts) & set(key_parts):  # 如果有交集，认为匹配
            return key,value  # 找到一个匹配项，直接返回
        elif value.get("kind") == "CursorKind.FUNCTION_TEMPLATE" and value.get("spelling") in aux_parts[0]:
            return key,value

    # 如果没有匹配项，返回 None
    return None, None



def extract_function_info(aux_function: str, method_definition: dict):
    """
    提取给定函数的信息，包括函数定义内容、调用的目标函数以及类型引用列表。

    Args:
        aux_function (str): 要提取信息的函数名。
        method_definition (dict): 包含函数信息的字典。

    Returns:
        tuple: (函数定义, 调用的目标函数, 类型引用列表)，如果未找到函数信息则返回 None。
    """

    type_definition_list = []
    aux_id = aux_function
    aux_info = method_definition.get(aux_function)
    if not aux_info:
        #启动近似查询
        aux_id,aux_info = approximate_match(aux_function,method_definition)
        if not aux_info:
            return None, None, None, aux_id


    try:
        # 提取函数的基本信息
        start_line = aux_info.get("start_line")
        end_line = aux_info.get("end_line")
        file_path = aux_info.get("file")

        # 提取函数内容
        function_definition = extract_lines(file_path, start_line, end_line)

        # 提目标函数调用
        target_function_called = aux_info.get("target_function_called")

        #提取类型定义
        type_ref_list = aux_info.get("type_ref_list")
        for type_ref in type_ref_list:

            type_def_info = type_ref.get("type_def")
            type_def_file = type_def_info.get("file")
            type_def_start_line = type_def_info.get("start_line")
            type_def_end_line = type_def_info.get("end_line")
            type_def_file_content = extract_lines(type_def_file, type_def_start_line, type_def_end_line)
            type_definition_list.append(type_def_file_content)

            flag = type_ref.get("flag")
            if flag:
                underlying_type_def_info = type_ref.get("underlying_type")
                underlying_type_def_file = underlying_type_def_info.get("file")
                underlying_type_def_start_line = underlying_type_def_info.get("start_line")
                underlying_type_def_end_line = underlying_type_def_info.get("end_line")
                underlying_type_def_file_content = extract_lines(underlying_type_def_file, underlying_type_def_start_line, underlying_type_def_end_line)
                type_definition_list.append(underlying_type_def_file_content)

        return function_definition, target_function_called, type_definition_list, aux_id
    except Exception as e:
        # 捕获潜在异常，避免程序中断
        raise ValueError(f"Error extracting information for function '{aux_function}': {e}")


def process_test_body(
    testCase: Dict[str, Any],
    method_definition: Dict[str, Any],
    call_graph: nx.Graph
) -> Dict[str, Any]:
    """
    处理单个测试用例，提取相关的函数调用信息、辅助函数和类型引用。

    Args:
        testCase (Dict[str, Any]): 单个测试用例信息，必须包含 "macro" 和 "testbody_id" 键。
        method_definition (Dict[str, Any]): 方法定义信息，用于提取函数信息。
        call_graph (nx.Graph): 调用图，用于辅助函数的提取。

    Returns:
        Dict[str, Any]: 包含以下键值对的结果字典：
            - target_function_call_in_this_testcase (Set[str]): 测试用例中调用的目标函数集合。
            - aux_function_in_this_testcase (Set[str]): 测试用例中的辅助函数集合。
            - type_ref_list_in_this_test_case (List[Dict[str, Any]]): 类型引用列表。
            - include_directives (List[str]): 测试用例的头文件引用。
    """
    # 初始化结果
    result: Dict[str, Any] = {
        "test_body":"",
        "target_function_call_in_this_testcase": set(),
        "aux_function_in_this_testcase": set(),
        "type_ref_list_in_this_test_case": [],
        "include_directives": [],
    }

    # 输入验证
    if not isinstance(testCase, dict):
        raise ValueError("testCase must be a dictionary.")
    if "macro" not in testCase or "testbody_id" not in testCase:
        raise ValueError("testCase must contain 'macro' and 'testbody_id' keys.")
    if not isinstance(method_definition, dict):
        raise ValueError("method_definition must be a dictionary.")

    # 提取头文件引用
    result["include_directives"] = testCase.get("include_directives", [])

    # 提取测试主体函数的信息
    testbody_id = testCase.get("testbody_id")
    testbody_definition, target_function_called_in_testbody, type_ref_list_in_testbody,_ = extract_function_info(
        testbody_id, method_definition
    )
    result["test_body"] = testbody_definition
    # 合并目标函数调用和类型引用信息
    result["target_function_call_in_this_testcase"].update(target_function_called_in_testbody)
    result["type_ref_list_in_this_test_case"].extend(type_ref_list_in_testbody)

    # 获取辅助函数列表并提取信息
    aux_function_call_list = preorder_traverse_with_networkx(call_graph, testbody_id)

    for aux_function in aux_function_call_list:
        function_definition, target_function_called, type_ref_list,_ = extract_function_info(
            aux_function, method_definition
        )


        if function_definition is  None:
            warnings.warn(f"Failed to extract function info for aux_function: {aux_function}\n"
                          f"This may be the default constructor for an implicitly-defined struct")
        else:

            result["aux_function_in_this_testcase"].add(function_definition)

            result["target_function_call_in_this_testcase"].update(target_function_called)

            # 避免重复添加类型引用
            for type_ref in type_ref_list:
                if type_ref not in result["type_ref_list_in_this_test_case"]:
                    result["type_ref_list_in_this_test_case"].append(type_ref)

    return result


def process_fixture_class(fixture_class_list:list, method_definition:Dict[str,Any],call_graph: nx.Graph):
    fixture_class_infos = []
    for fixture_class in fixture_class_list:
        #print(fixture_class.get("fixture_class_name"))
        fixture_class_defnition_info = fixture_class.get("fixtur_definition")
        fixture_class_defnition_file = fixture_class_defnition_info.get("file")
        fixture_class_defnition_start_line = fixture_class_defnition_info.get("start_line")
        fixture_class_defnition_end_line = fixture_class_defnition_info.get("end_line")

        fixture_class_defnition = extract_lines(fixture_class_defnition_file,fixture_class_defnition_start_line,fixture_class_defnition_end_line)

        cxx_method_list = fixture_class.get("cxx_method_list")

        cxx_target_function_called_in_fixture = set()
        cxxmethod_definition_in_fixture = set()
        cxx_type_ref_set_in_fixture = set()
        aux_function_in_fixture_list = set()


        #分析成员函数
        for cxx_method in cxx_method_list:
            isSrcCode = cxx_method.get("isSrcCode")
            cxxmethod_id = cxx_method.get("cxxmethod_id")

            #取成员函数的信息
            cxxmethod_definition, cxx_target_calld_list, cxx_type_ref_list, cxxmethod_id = extract_function_info(
                cxxmethod_id, method_definition)
            #将成员函数中的信息存入
            if cxx_target_calld_list is not None:
                cxx_target_function_called_in_fixture.update(cxx_target_calld_list)
            if not isSrcCode:
                cxxmethod_definition_in_fixture.add(cxxmethod_definition)
            if cxx_type_ref_list is not None:
                cxx_type_ref_set_in_fixture.update(set(cxx_type_ref_list))


            #取成员函数所调用的辅助函数信息
            cxx_aux_method_list = preorder_traverse_with_networkx(call_graph,cxxmethod_id)

            for cxx_aux_method in cxx_aux_method_list:
                aux_method_definition, aux_target_called_list, aux_type_ref_list, _ =  extract_function_info(cxx_aux_method, method_definition)
                if aux_method_definition is not None:
                    aux_function_in_fixture_list.add(aux_method_definition)
                if aux_target_called_list is not None:
                    cxx_target_function_called_in_fixture.update(set(aux_target_called_list))
                if aux_type_ref_list is not None:
                    cxx_type_ref_set_in_fixture.update(set(aux_type_ref_list))


        type_def_list_in_fixture = fixture_class.get("type_def_list_in_fixture")
        for type_ref in type_def_list_in_fixture:
            type_def_info = type_ref.get("type_def")
            type_def_file = type_def_info.get("file")
            type_def_start_line = type_def_info.get("start_line")
            type_def_end_line = type_def_info.get("end_line")
            type_def_file_content = extract_lines(type_def_file, type_def_start_line, type_def_end_line)
            cxx_type_ref_set_in_fixture.add(type_def_file_content)

            flag = type_ref.get("flag")
            if flag:
                underlying_type_def_info = type_ref.get("underlying_type")
                underlying_type_def_file = underlying_type_def_info.get("file")
                underlying_type_def_start_line = underlying_type_def_info.get("start_line")
                underlying_type_def_end_line = underlying_type_def_info.get("end_line")
                underlying_type_def_file_content = extract_lines(underlying_type_def_file,
                                                                 underlying_type_def_start_line,
                                                                 underlying_type_def_end_line)
                cxx_type_ref_set_in_fixture.add(underlying_type_def_file_content)

        fixture_class_info = {
            "fixture_class_defnition":fixture_class_defnition,
            "cxx_target_function_called_in_fixture":list(cxx_target_function_called_in_fixture),
            "cxxmethod_definition_in_fixture":list(cxxmethod_definition_in_fixture),
            "cxx_type_ref_set_in_fixture":list(cxx_type_ref_set_in_fixture),
            "aux_function_in_fixture":list(aux_function_in_fixture_list)
        }
        fixture_class_infos.append(fixture_class_info)
    return fixture_class_infos

'''
s = parse_test_case_source("/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test/testCase_info.json")
method_definition = parse_test_case_source("/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test/method_definitions.json")
var_infos = parse_test_case_source("/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test/var_infos.json")
class_infos = parse_test_case_source("/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test/class_infos.json")
evalgen_infos = parse_test_case_source("/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test/evalgen_infos.json")
testcase_to_evlgen = parse_test_case_source("/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test/testcase_to_evalgen.json")

json_path: str = "/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test/call_graph_all.json"

# 构建函数调用图
call_graph: nx.DiGraph = build_function_call_graph(json_path)

test_case_all = []

for file,test_case_list in s.items():

    for testCase in test_case_list:
        ##下面内容可以封装成一个函数

        macro = testCase.get("macro")

        if macro == "TEST":
            test_body = process_test_body(testCase, method_definition, call_graph)
            test_body = process_test_body(testCase, method_definition, call_graph)

            # 定义变量存储数据
            target_function_call_in_test_case = []
            aux_function_int_test_case = []
            type_reference_in_test_case = []
            include_directives_in_test_case = testCase.get("include_directives")
            macro_definitions = []

            macro_definition_info_list = testCase.get("macro_definition")

            for macro_definition_info in macro_definition_info_list:
                macro_file = macro_definition_info.get("file")
                macro_start_line = macro_definition_info.get("start_line")
                macro_end_line = macro_definition_info.get("end_line")
                macro_definiiton = extract_lines(macro_file, macro_start_line, macro_end_line)
                macro_definitions.append(macro_definiiton)



            # 处理 test_body
            test_body_definition = test_body.get("test_body")
            target_functions_call_in_testbody = test_body.get("target_function_call_in_this_testcase")
            for target_function in target_functions_call_in_testbody:
                if target_function not in target_function_call_in_test_case:
                    target_function_call_in_test_case.append(target_function)

            aux_function_in_testbody = test_body.get("aux_function_in_this_testcase")
            for aux_function in aux_function_in_testbody:
                if aux_function not in aux_function_int_test_case:
                    aux_function_int_test_case.append(aux_function)

            type_ref_list_in_test_body = test_body.get("type_ref_list_in_this_test_case")
            for type_ref in type_ref_list_in_test_body:
                if type_ref not in type_reference_in_test_case:
                    type_reference_in_test_case.append(type_ref)

            test_case = {
                "macro": macro,
                "file":file,
                "macro_definition":macro_definitions,
                "include_directives_in_test_case": include_directives_in_test_case,
                "test_body_definition": test_body_definition,
                "target_function_call_in_test_case": target_function_call_in_test_case,
                "aux_function_int_test_case": aux_function_int_test_case,
                "type_reference_in_test_case": type_reference_in_test_case,
            }
            test_case_all.append(test_case)


        elif macro == "TEST_P":

            test_body = process_test_body(testCase, method_definition, call_graph)

            fixture_class_list =testCase.get("fixture_class")

            fixture_class_infos = process_fixture_class(fixture_class_list,method_definition,call_graph)

            test_case_id = testCase.get("test_case_id")

            eval_list = extract_evalgen_info(test_case_id,evalgen_infos,testcase_to_evlgen,var_infos,call_graph,class_infos,method_definition)

            if eval_list is None:
                continue
            #下面处理参数生成器
            for eval in eval_list:

                fixture_definitions_in_test_case = []
                target_function_call_in_test_case = []
                cxxmethod_definition_in_test_case = []
                type_reference_in_test_case = []
                aux_function_int_test_case = []
                include_directives_in_test_case = testCase.get("include_directives")
                var_list_in_test_case = []
                class_list_in_test_case = []
                macro_definitions = []



                #处理宏定义
                macro_definition_info_list = testCase.get("macro_definition")
                for macro_definition_info in macro_definition_info_list:
                    macro_file = macro_definition_info.get("file")
                    macro_start_line = macro_definition_info.get("start_line")
                    macro_end_line = macro_definition_info.get("end_line")
                    macro_definiiton = extract_lines(macro_file, macro_start_line, macro_end_line)
                    macro_definitions.append(macro_definiiton)


                # 处理testbody
                test_body_definition = test_body.get("test_body")
                target_functions_call_in_testbody = test_body.get("target_function_call_in_this_testcase")
                for target_function in target_functions_call_in_testbody:
                    if target_function not in target_function_call_in_test_case:
                        target_function_call_in_test_case.append(target_function)

                aux_function_in_testbody = test_body.get("aux_function_in_this_testcase")
                for aux_function in aux_function_in_testbody:
                    if aux_function not in aux_function_int_test_case:
                        aux_function_int_test_case.append(aux_function)

                type_ref_list_in_test_body = test_body.get("type_ref_list_in_this_test_case")
                for type_ref in type_ref_list_in_test_body:
                    if type_ref not in type_reference_in_test_case:
                        type_reference_in_test_case.append(type_ref)

                # 下面处理测试夹具
                for fixture_class_info in fixture_class_infos:

                    fixture_definition = fixture_class_info.get("fixture_class_defnition")
                    if fixture_definition not in fixture_definitions_in_test_case:
                        fixture_definitions_in_test_case.append(fixture_definition)

                    target_functions_call_in_fixture = fixture_class_info.get("cxx_target_function_called_in_fixture")
                    for target_in_ficture in target_functions_call_in_fixture:
                        if target_in_ficture not in target_function_call_in_test_case:
                            target_function_call_in_test_case.append(target_in_ficture)

                    cxxmethods_definition_in_fixture = fixture_class_info.get("cxxmethod_definition_in_fixture")
                    for cxx_method_definition in cxxmethods_definition_in_fixture:
                        if cxx_method_definition not in cxxmethod_definition_in_test_case:
                            cxxmethod_definition_in_test_case.append(cxx_method_definition)

                    types_reference_in_fixture = fixture_class_info.get("cxx_type_ref_set_in_fixture")
                    for type_reference in types_reference_in_fixture:
                        if type_reference not in type_reference_in_test_case:
                            type_reference_in_test_case.append(type_reference)

                    aux_functions_in_fixture = fixture_class_info.get("aux_function_in_fixture")
                    for aux_function in aux_functions_in_fixture:
                        if aux_function not in aux_function_int_test_case:
                            aux_function_int_test_case.append(aux_function)

                evalgen_definition = eval.get("evalgen_definition")

                aux_definition_in_eval_all = eval.get("aux_definition_in_eval_all")
                for aux_function in aux_definition_in_eval_all:
                    if aux_function not in aux_function_int_test_case:
                        aux_function_int_test_case.append(aux_function)

                target_function_call_in_eval_all = eval.get("target_function_call_in_eval_all")
                for target_function in target_function_call_in_eval_all:
                    if target_function not in target_function_call_in_test_case:
                        target_function_call_in_test_case.append(target_function)

                var_ref_set = eval.get("var_ref_set")
                for var_ref in var_ref_set:
                    if var_ref not in var_list_in_test_case:
                        var_list_in_test_case.append(var_ref)

                type_ref_list_in_eval_all = eval.get("type_ref_set_in_eval_all")
                for type_ref in type_ref_list_in_eval_all:
                    if type_ref not in type_reference_in_test_case:
                        type_reference_in_test_case.append(type_ref)

                class_ref_definition_set = eval.get("class_ref_definition_set")
                for class_ref in class_ref_definition_set:
                    if class_ref not in class_list_in_test_case:
                        class_list_in_test_case.append(class_ref)

                test_case = {
                    "macro":macro,
                    "file": file,
                    "include_directives_in_test_case":include_directives_in_test_case,
                    "macro_definition":macro_definitions,
                    "fixture_definitions_in_test_case":fixture_definitions_in_test_case,
                    "test_body_definition":test_body_definition,
                    "target_function_call_in_test_case":target_function_call_in_test_case,
                    "cxxmethod_definition_in_test_case":cxxmethod_definition_in_test_case,
                    "type_reference_in_test_case":type_reference_in_test_case,
                    "aux_function_int_test_case":aux_function_int_test_case,
                    "evalgen_definition":evalgen_definition,
                    "var_list_in_test_case":var_list_in_test_case,
                    "class_list_in_test_case":class_list_in_test_case
                }
                test_case_all.append(test_case)

        elif macro == "TEST_F":

            test_body = process_test_body(testCase, method_definition, call_graph)
            fixture_class_list = testCase.get("fixture_class")

            fixture_class_infos = process_fixture_class(fixture_class_list, method_definition, call_graph)

            # 定义变量存储数据
            fixture_definitions_in_test_case = []
            target_function_call_in_test_case = []
            cxxmethod_definition_in_test_case = []
            type_reference_in_test_case = []
            aux_function_int_test_case = []
            include_directives_in_test_case = testCase.get("include_directives")
            macro_definitions = []

            # 处理宏定义
            macro_definition_info_list = testCase.get("macro_definition")
            for macro_definition_info in macro_definition_info_list:
                macro_file = macro_definition_info.get("file")
                macro_start_line = macro_definition_info.get("start_line")
                macro_end_line = macro_definition_info.get("end_line")
                macro_definiiton = extract_lines(macro_file, macro_start_line, macro_end_line)
                macro_definitions.append(macro_definiiton)


            # 处理 test_body
            test_body_definition = test_body.get("test_body")
            target_functions_call_in_testbody = test_body.get("target_function_call_in_this_testcase")
            for target_function in target_functions_call_in_testbody:
                if target_function not in target_function_call_in_test_case:
                    target_function_call_in_test_case.append(target_function)

            aux_function_in_testbody = test_body.get("aux_function_in_this_testcase")
            for aux_function in aux_function_in_testbody:
                if aux_function not in aux_function_int_test_case:
                    aux_function_int_test_case.append(aux_function)

            type_ref_list_in_test_body = test_body.get("type_ref_list_in_this_test_case")
            for type_ref in type_ref_list_in_test_body:
                if type_ref not in type_reference_in_test_case:
                    type_reference_in_test_case.append(type_ref)

            # 处理测试夹具
            for fixture_class_info in fixture_class_infos:

                fixture_definition = fixture_class_info.get("fixture_class_defnition")
                if fixture_definition not in fixture_definitions_in_test_case:
                    fixture_definitions_in_test_case.append(fixture_definition)

                target_functions_call_in_fixture = fixture_class_info.get("cxx_target_function_called_in_fixture")
                for target_in_fixture in target_functions_call_in_fixture:
                    if target_in_fixture not in target_function_call_in_test_case:
                        target_function_call_in_test_case.append(target_in_fixture)

                cxxmethods_definition_in_fixture = fixture_class_info.get("cxxmethod_definition_in_fixture")
                for cxx_method_definition in cxxmethods_definition_in_fixture:
                    if cxx_method_definition not in cxxmethod_definition_in_test_case:
                        cxxmethod_definition_in_test_case.append(cxx_method_definition)

                types_reference_in_fixture = fixture_class_info.get("cxx_type_ref_set_in_fixture")
                for type_reference in types_reference_in_fixture:
                    if type_reference not in type_reference_in_test_case:
                        type_reference_in_test_case.append(type_reference)

                aux_functions_in_fixture = fixture_class_info.get("aux_function_in_fixture")
                for aux_function in aux_functions_in_fixture:
                    if aux_function not in aux_function_int_test_case:
                        aux_function_int_test_case.append(aux_function)

            test_case = {
                "macro": macro,
                "file": file,
                "include_directives_in_test_case": include_directives_in_test_case,
                "macro_definition":macro_definitions,
                "fixture_definitions_in_test_case": fixture_definitions_in_test_case,
                "test_body_definition": test_body_definition,
                "target_function_call_in_test_case": target_function_call_in_test_case,
                "cxxmethod_definition_in_test_case": cxxmethod_definition_in_test_case,
                "type_reference_in_test_case": type_reference_in_test_case,
                "aux_function_int_test_case": aux_function_int_test_case,
            }

            test_case_all.append(test_case)
'''


def process_all_test_cases(
    testcase_path: str,
    method_definition_path: str,
    var_infos_path: str,
    class_infos_path: str,
    evalgen_infos_path: str,
    testcase_to_evlgen_path: str,
    call_graph_json_path: str,
    output_path: str
):
    # 从给定路径中解析测试数据
    testcase = parse_test_case_source(testcase_path)
    method_definition = parse_test_case_source(method_definition_path)
    var_infos = parse_test_case_source(var_infos_path)
    class_infos = parse_test_case_source(class_infos_path)
    evalgen_infos = parse_test_case_source(evalgen_infos_path)
    testcase_to_evlgen = parse_test_case_source(testcase_to_evlgen_path)

    # 构建函数调用图
    call_graph: nx.DiGraph = build_function_call_graph(call_graph_json_path)

    test_case_all = []

    for file, test_case_list in testcase.items():
        for testCase in test_case_list:
            macro = testCase.get("macro")

            if macro == "TEST":
                test_body = process_test_body(testCase, method_definition, call_graph)

                # 定义变量存储数据
                target_function_call_in_test_case = []
                aux_function_int_test_case = []
                type_reference_in_test_case = []
                include_directives_in_test_case = testCase.get("include_directives")
                macro_definitions = []

                macro_definition_info_list = testCase.get("macro_definition", [])
                for macro_definition_info in macro_definition_info_list:
                    macro_file = macro_definition_info.get("file")
                    macro_start_line = macro_definition_info.get("start_line")
                    macro_end_line = macro_definition_info.get("end_line")
                    macro_definiiton = extract_lines(macro_file, macro_start_line, macro_end_line)
                    macro_definitions.append(macro_definiiton)

                # 处理 test_body
                test_body_definition = test_body.get("test_body")
                target_functions_call_in_testbody = test_body.get("target_function_call_in_this_testcase", [])
                for target_function in target_functions_call_in_testbody:
                    if target_function not in target_function_call_in_test_case:
                        target_function_call_in_test_case.append(target_function)

                aux_function_in_testbody = test_body.get("aux_function_in_this_testcase", [])
                for aux_function in aux_function_in_testbody:
                    if aux_function not in aux_function_int_test_case:
                        aux_function_int_test_case.append(aux_function)

                type_ref_list_in_test_body = test_body.get("type_ref_list_in_this_test_case", [])
                for type_ref in type_ref_list_in_test_body:
                    if type_ref not in type_reference_in_test_case:
                        type_reference_in_test_case.append(type_ref)

                test_case_dict = {
                    "macro": macro,
                    "file": file,
                    "macro_definition": macro_definitions,
                    "include_directives_in_test_case": include_directives_in_test_case,
                    "test_body_definition": test_body_definition,
                    "target_function_call_in_test_case": target_function_call_in_test_case,
                    "aux_function_int_test_case": aux_function_int_test_case,
                    "type_reference_in_test_case": type_reference_in_test_case,
                }
                test_case_all.append(test_case_dict)

            elif macro == "TEST_P":
                test_body = process_test_body(testCase, method_definition, call_graph)

                fixture_class_list = testCase.get("fixture_class")
                fixture_class_infos = process_fixture_class(fixture_class_list, method_definition, call_graph)

                test_case_id = testCase.get("test_case_id")

                eval_list = extract_evalgen_info(test_case_id, evalgen_infos, testcase_to_evlgen, var_infos, call_graph, class_infos, method_definition)

                if eval_list is None:
                    continue

                # 下面处理参数生成器
                for eval_info in eval_list:
                    fixture_definitions_in_test_case = []
                    target_function_call_in_test_case = []
                    cxxmethod_definition_in_test_case = []
                    type_reference_in_test_case = []
                    aux_function_int_test_case = []
                    include_directives_in_test_case = testCase.get("include_directives")
                    var_list_in_test_case = []
                    class_list_in_test_case = []
                    macro_definitions = []

                    # 处理宏定义
                    macro_definition_info_list = testCase.get("macro_definition", [])
                    for macro_definition_info in macro_definition_info_list:
                        macro_file = macro_definition_info.get("file")
                        macro_start_line = macro_definition_info.get("start_line")
                        macro_end_line = macro_definition_info.get("end_line")
                        macro_definiiton = extract_lines(macro_file, macro_start_line, macro_end_line)
                        macro_definitions.append(macro_definiiton)

                    # 处理testbody
                    test_body_definition = test_body.get("test_body")
                    target_functions_call_in_testbody = test_body.get("target_function_call_in_this_testcase", [])
                    for target_function in target_functions_call_in_testbody:
                        if target_function not in target_function_call_in_test_case:
                            target_function_call_in_test_case.append(target_function)

                    aux_function_in_testbody = test_body.get("aux_function_in_this_testcase", [])
                    for aux_function in aux_function_in_testbody:
                        if aux_function not in aux_function_int_test_case:
                            aux_function_int_test_case.append(aux_function)

                    type_ref_list_in_test_body = test_body.get("type_ref_list_in_this_test_case", [])
                    for type_ref in type_ref_list_in_test_body:
                        if type_ref not in type_reference_in_test_case:
                            type_reference_in_test_case.append(type_ref)

                    # 处理测试夹具
                    for fixture_class_info in fixture_class_infos:
                        fixture_definition = fixture_class_info.get("fixture_class_defnition")
                        if fixture_definition not in fixture_definitions_in_test_case:
                            fixture_definitions_in_test_case.append(fixture_definition)

                        target_functions_call_in_fixture = fixture_class_info.get("cxx_target_function_called_in_fixture", [])
                        for target_in_fixture in target_functions_call_in_fixture:
                            if target_in_fixture not in target_function_call_in_test_case:
                                target_function_call_in_test_case.append(target_in_fixture)

                        cxxmethods_definition_in_fixture = fixture_class_info.get("cxxmethod_definition_in_fixture", [])
                        for cxx_method_definition in cxxmethods_definition_in_fixture:
                            if cxx_method_definition not in cxxmethod_definition_in_test_case:
                                cxxmethod_definition_in_test_case.append(cxx_method_definition)

                        types_reference_in_fixture = fixture_class_info.get("cxx_type_ref_set_in_fixture", [])
                        for type_reference in types_reference_in_fixture:
                            if type_reference not in type_reference_in_test_case:
                                type_reference_in_test_case.append(type_reference)

                        aux_functions_in_fixture = fixture_class_info.get("aux_function_in_fixture", [])
                        for aux_function in aux_functions_in_fixture:
                            if aux_function not in aux_function_int_test_case:
                                aux_function_int_test_case.append(aux_function)

                    evalgen_definition = eval_info.get("evalgen_definition")

                    aux_definition_in_eval_all = eval_info.get("aux_definition_in_eval_all", [])
                    for aux_function in aux_definition_in_eval_all:
                        if aux_function not in aux_function_int_test_case:
                            aux_function_int_test_case.append(aux_function)

                    target_function_call_in_eval_all = eval_info.get("target_function_call_in_eval_all", [])
                    for target_function in target_function_call_in_eval_all:
                        if target_function not in target_function_call_in_test_case:
                            target_function_call_in_test_case.append(target_function)

                    var_ref_set = eval_info.get("var_ref_set", [])
                    for var_ref in var_ref_set:
                        if var_ref not in var_list_in_test_case:
                            var_list_in_test_case.append(var_ref)

                    type_ref_list_in_eval_all = eval_info.get("type_ref_set_in_eval_all", [])
                    for type_ref in type_ref_list_in_eval_all:
                        if type_ref not in type_reference_in_test_case:
                            type_reference_in_test_case.append(type_ref)

                    class_ref_definition_set = eval_info.get("class_ref_definition_set", [])
                    for class_ref in class_ref_definition_set:
                        if class_ref not in class_list_in_test_case:
                            class_list_in_test_case.append(class_ref)

                    test_case_dict = {
                        "macro": macro,
                        "file": file,
                        "include_directives_in_test_case": include_directives_in_test_case,
                        "macro_definition": macro_definitions,
                        "fixture_definitions_in_test_case": fixture_definitions_in_test_case,
                        "test_body_definition": test_body_definition,
                        "target_function_call_in_test_case": target_function_call_in_test_case,
                        "cxxmethod_definition_in_test_case": cxxmethod_definition_in_test_case,
                        "type_reference_in_test_case": type_reference_in_test_case,
                        "aux_function_int_test_case": aux_function_int_test_case,
                        "evalgen_definition": evalgen_definition,
                        "var_list_in_test_case": var_list_in_test_case,
                        "class_list_in_test_case": class_list_in_test_case
                    }
                    test_case_all.append(test_case_dict)

            elif macro == "TEST_F":
                test_body = process_test_body(testCase, method_definition, call_graph)
                fixture_class_list = testCase.get("fixture_class")

                fixture_class_infos = process_fixture_class(fixture_class_list, method_definition, call_graph)

                # 定义变量存储数据
                fixture_definitions_in_test_case = []
                target_function_call_in_test_case = []
                cxxmethod_definition_in_test_case = []
                type_reference_in_test_case = []
                aux_function_int_test_case = []
                include_directives_in_test_case = testCase.get("include_directives")
                macro_definitions = []

                # 处理宏定义
                macro_definition_info_list = testCase.get("macro_definition", [])
                for macro_definition_info in macro_definition_info_list:
                    macro_file = macro_definition_info.get("file")
                    macro_start_line = macro_definition_info.get("start_line")
                    macro_end_line = macro_definition_info.get("end_line")
                    macro_definiiton = extract_lines(macro_file, macro_start_line, macro_end_line)
                    macro_definitions.append(macro_definiiton)

                # 处理 test_body
                test_body_definition = test_body.get("test_body")
                target_functions_call_in_testbody = test_body.get("target_function_call_in_this_testcase", [])
                for target_function in target_functions_call_in_testbody:
                    if target_function not in target_function_call_in_test_case:
                        target_function_call_in_test_case.append(target_function)

                aux_function_in_testbody = test_body.get("aux_function_in_this_testcase", [])
                for aux_function in aux_function_in_testbody:
                    if aux_function not in aux_function_int_test_case:
                        aux_function_int_test_case.append(aux_function)

                type_ref_list_in_test_body = test_body.get("type_ref_list_in_this_test_case", [])
                for type_ref in type_ref_list_in_test_body:
                    if type_ref not in type_reference_in_test_case:
                        type_reference_in_test_case.append(type_ref)

                # 处理测试夹具
                for fixture_class_info in fixture_class_infos:
                    fixture_definition = fixture_class_info.get("fixture_class_defnition")
                    if fixture_definition not in fixture_definitions_in_test_case:
                        fixture_definitions_in_test_case.append(fixture_definition)

                    target_functions_call_in_fixture = fixture_class_info.get("cxx_target_function_called_in_fixture", [])
                    for target_in_fixture in target_functions_call_in_fixture:
                        if target_in_fixture not in target_function_call_in_test_case:
                            target_function_call_in_test_case.append(target_in_fixture)

                    cxxmethods_definition_in_fixture = fixture_class_info.get("cxxmethod_definition_in_fixture", [])
                    for cxx_method_definition in cxxmethods_definition_in_fixture:
                        if cxx_method_definition not in cxxmethod_definition_in_test_case:
                            cxxmethod_definition_in_test_case.append(cxx_method_definition)

                    types_reference_in_fixture = fixture_class_info.get("cxx_type_ref_set_in_fixture", [])
                    for type_reference in types_reference_in_fixture:
                        if type_reference not in type_reference_in_test_case:
                            type_reference_in_test_case.append(type_reference)

                    aux_functions_in_fixture = fixture_class_info.get("aux_function_in_fixture", [])
                    for aux_function in aux_functions_in_fixture:
                        if aux_function not in aux_function_int_test_case:
                            aux_function_int_test_case.append(aux_function)

                test_case_dict = {
                    "macro": macro,
                    "file": file,
                    "include_directives_in_test_case": include_directives_in_test_case,
                    "macro_definition": macro_definitions,
                    "fixture_definitions_in_test_case": fixture_definitions_in_test_case,
                    "test_body_definition": test_body_definition,
                    "target_function_call_in_test_case": target_function_call_in_test_case,
                    "cxxmethod_definition_in_test_case": cxxmethod_definition_in_test_case,
                    "type_reference_in_test_case": type_reference_in_test_case,
                    "aux_function_int_test_case": aux_function_int_test_case,
                }

                test_case_all.append(test_case_dict)

    # 将结果写入 JSON 文件
    with open(output_path, "w") as f:
        json.dump(test_case_all, f, indent=4)

    return test_case_all

if __name__ == "__main__":
    testcase_path = "/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test/testCase_info.json"
    method_definition_path = "/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test/method_definitions.json"
    var_infos_path = "/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test/var_infos.json"
    class_infos_path = "/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test/class_infos.json"
    evalgen_infos_path = "/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test/evalgen_infos.json"
    testcase_to_evlgen_path = "/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test/testcase_to_evalgen.json"
    call_graph_json_path = "/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test/call_graph_all.json"
    output_path = "testcase.json"

    result = process_all_test_cases(testcase_path, method_definition_path, var_infos_path, class_infos_path, evalgen_infos_path, testcase_to_evlgen_path, call_graph_json_path, output_path)


    def make_hashable(obj):
        """
        递归将字典、列表等可变对象转换为可哈希对象
        """
        if isinstance(obj, dict):
            return frozenset((key, make_hashable(value)) for key, value in obj.items())
        elif isinstance(obj, list):
            return tuple(make_hashable(item) for item in obj)
        else:
            return obj


    def has_duplicate_dicts(arr):
        """
        判断数组中是否有重复的字典
        :param arr: 包含字典的列表
        :return: 布尔值，True表示有重复字典，False表示没有
        """
        seen = set()  # 用于存储哈希化后的字典
        for d in arr:
            if isinstance(d, dict):  # 确保元素是字典
                immutable_d = make_hashable(d)
                if immutable_d in seen:  # 如果已经存在，说明有重复
                    return True
                seen.add(immutable_d)
            else:
                raise ValueError("数组中的元素不是字典")
        return False


    res = has_duplicate_dicts(result)
    print(len(result))
    print("数组中有重复字典吗？", res)




