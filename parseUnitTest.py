from utils import load_compile_commands, load_public_api, process_compile_args, is_path_contained_in, write_dict_to_json_in_dir, is_path_contained_in_any,generate_unique_cursor_id
from clang.cindex import Cursor
from clang import cindex  # 导入 Clang 的 Python 接口模块
from typing import List, Tuple, Optional, Dict, Any, Set
import os
from tqdm import tqdm


# 设置 Clang 库的路径
cindex.Config.set_library_file('/usr/lib/llvm-15/lib/libclang.so.1')


def analyze_class(
        cursor:Cursor,
        target_lib_dir:str
) -> Dict[str, Any]:


    class_name = cursor.spelling
    type_def_list_in_class = []  # 存储测试夹具中引用的类型

    # 取其定义位置
    class_definition = {
        "file": cursor.location.file.name if cursor.location.file else "",
        "start_line": cursor.extent.start.line,
        "end_line": cursor.extent.end.line
    }

    # 初始化cxx方法列表
    cxx_method_list = []

    # 取成员函数类型
    cxx_method_type = (
        cindex.CursorKind.CXX_METHOD,
        cindex.CursorKind.FUNCTION_TEMPLATE,
        cindex.CursorKind.CONSTRUCTOR,
        cindex.CursorKind.DESTRUCTOR,
        cindex.CursorKind.CONVERSION_FUNCTION
    )

    for child in cursor.walk_preorder():
        # 存储在测试夹具中被使用的类型
        field_type_in_fixture = []

        # 分析成员变量
        if child.kind == cindex.CursorKind.FIELD_DECL:
            for filed_child in child.get_children():
                if filed_child.kind == cindex.CursorKind.TYPE_REF:
                    filed_child_referenced_name = filed_child.location.file.name
                    if is_path_contained_in(target_lib_dir, filed_child_referenced_name):
                        field_type_in_fixture.append(filed_child.referenced)

        # 处理成员变量的类型定义
        for field_type_ref in field_type_in_fixture:
            field_type_def = get_type_ref_definition(field_type_ref, target_lib_dir)
            if field_type_def is not None:
                type_def_list_in_class.append(field_type_def)

        # 分析成员函数
        if child.kind in cxx_method_type:

            isSrcCode = child.is_definition()

            front_2 = child.get_usr()
            back_2 = generate_unique_cursor_id(child)
            cxxmethod_id = f'{front_2} & {back_2}'

            cxx_method_info = {
                "cxxmethod_id": cxxmethod_id,
                "isSrcCode": isSrcCode
            }

            cxx_method_list.append(cxx_method_info)

    class_info = {
        "class_name": class_name,
        "class_definition": class_definition,
        "cxx_method_list": cxx_method_list,
        "type_def_list_in_class": type_def_list_in_class,
    }


    # 生成测试用例并返回
    return class_info




def determine_if_is_fixture(
    class_cursor: cindex.Cursor,
    root_cursor: cindex.Cursor,
    class_def_list: List,
    ignore_type_path: List,
    checked_classes=None
) -> str:

    # 初始化默认值
    checked_classes = checked_classes or set()

    # 初始返回值和基类列表
    base_class_list = []
    result_final = 'None'

    # 确保输入是类声明
    if class_cursor.kind not in [cindex.CursorKind.CLASS_DECL, cindex.CursorKind.CLASS_TEMPLATE]:
        return result_final

    # 防止循环继承导致的无限递归
    class_usr = class_cursor.get_usr()
    if class_usr in checked_classes:
        return result_final
    checked_classes.add(class_usr)

    # 查找当前类的所有基类
    for class_def in class_def_list:
        if class_def.spelling == class_cursor.spelling:
            base_class_list.append(class_def)
            break

    # 遍历基类，递归查找最终基类
    for base_cursor in base_class_list:
        for base in base_cursor.get_children():
            if base.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
                base_type = base.type
                base_decl = base_type.get_declaration()
                base_usr = base_decl.get_usr()
                # 检查基类是否为 GTest 类型
                if base_usr == 'c:@N@testing@S@Test':
                    result_final = 'Test'
                elif base_usr.startswith('c:@N@testing@ST>1#T@TestWithParam') or base_usr.startswith('c:@N@testing@ST>1#T@WithParamInterface'):
                    result_final = 'TestWithParam'
                else:
                    # 递归检查基类
                    result = determine_if_is_fixture(
                        base_decl, root_cursor, class_def_list, ignore_type_path, checked_classes
                    )
                    if result != 'None':
                        result_final = result

    return result_final




def get_var_info(cursor: cindex.Cursor, src_file: str, target_function_call: List[str], method_type: Set[cindex.CursorKind], unit_test_dir: str, target_lib_dir: str) -> Dict:
    """
    获取变量声明的详细信息。

    参数：
    - cursor: cindex.Cursor - 当前遍历的游标。
    - src_file: str - 源文件路径。
    - target_function_call: Set[str] - 被测目标函数集合。
    - method_type: Set[cindex.CursorKind] - 方法类型集合。
    - unit_test_dir: str - 单元测试目录路径。
    - target_lib_dir: str - 目标库目录路径。

    返回值：
    - Dict - 包含变量信息的字典。
    """
    var_def_file = cursor.location.file.name
    var_def_start_line = cursor.extent.start.line
    var_def_end_line = cursor.extent.end.line
    var_definition = {
        "file": var_def_file,
        "start_line": var_def_start_line,
        "end_line": var_def_end_line,
    }
    target_functions_call_in_var = set()
    aux_functions_call_in_var = set()
    var_type_ref_list = []
    var_aux_classes = set()

    # 取变量声明的定义
    for child in cursor.walk_preorder():
        child_ref = child.referenced
        if child.kind == cindex.CursorKind.DECL_REF_EXPR:
            if child_ref is not None:
                ref_def = child_ref.get_definition()
                if child_ref.kind == cindex.CursorKind.FUNCTION_DECL and child_ref.spelling in target_function_call:
                    # 取变量中所引用的被测目标函数
                    target_functions_call_in_var.add(child.spelling)
                elif ref_def and child_ref.kind in method_type and is_path_contained_in(unit_test_dir, ref_def.location.file.name):
                    # 取变量中引用的辅助函数
                    front_6 = ref_def.get_usr()
                    back_6 = generate_unique_cursor_id(ref_def)
                    aux_id = f'{front_6} & {back_6}'
                    aux_functions_call_in_var.add(aux_id)
        if child.kind == cindex.CursorKind.TYPE_REF:
            if child_ref is not None:
                ref_def = child_ref.get_definition()
                ref_def_location = ref_def.location.file.name
                if is_path_contained_in(unit_test_dir,ref_def_location):
                    if ref_def.kind != cindex.CursorKind.CLASS_DECL :
                        ref_def_info = get_type_ref_definition(ref_def, target_lib_dir)
                        var_type_ref_list.append(ref_def_info)
                    else:
                        front_7 = ref_def.get_usr()
                        back_7 = generate_unique_cursor_id(ref_def)
                        aux_id = f'{front_7} & {back_7}'
                        var_aux_classes.add(aux_id)

    var_info = {
        "var_name": cursor.spelling,
        "var_definition": var_definition,
        "target_functions_call_in_var": list(target_functions_call_in_var),
        "aux_functions_call_in_var": list(aux_functions_call_in_var),
        "var_type_ref_list": var_type_ref_list,
        "var_aux_classes": list(var_aux_classes)
    }

    return var_info


def get_function_call_graph(cursor: cindex.Cursor, unit_test_dir: str) -> List[str]:

    # 取函数类型
    function_type = (
        cindex.CursorKind.CXX_METHOD,
        cindex.CursorKind.FUNCTION_TEMPLATE,
        cindex.CursorKind.CONSTRUCTOR,
        cindex.CursorKind.DESTRUCTOR,
        cindex.CursorKind.CONVERSION_FUNCTION,
        cindex.CursorKind.FUNCTION_DECL
    )
    called_function_list = set()

    if cursor.is_definition():
        for child in cursor.walk_preorder():

            # 检查当前节点是否是函数调用
            if child.kind == cindex.CursorKind.CALL_EXPR and child.spelling != cursor.spelling:  # 防止递归调用
                referenced = child.referenced

                if referenced and referenced.location.file and referenced.kind in function_type:
                    try:
                        referenced_path = referenced.location.file.name
                        # 检查路径是否在指定目录中
                        if is_path_contained_in(unit_test_dir, referenced_path):
                            # 构造函数名称
                            front_1 = referenced.get_usr()
                            back_1 = generate_unique_cursor_id(referenced)
                            called_function_name = f'{front_1} & {back_1}'
                            called_function_list.add(called_function_name)  # 去重
                    except AttributeError as e:
                        # 捕获可能的异常
                        print(f"AttributeError encountered: {e}")
                    except Exception as e:
                        # 捕获其他异常并打印日志以供调试
                        print(f"Unexpected error encountered: {e}")

    return list(called_function_list)


def analyze_test_p_macro(
        cursor:Cursor,
        class_cursor_list: List[cindex.Cursor],
        include_directives: Set[str],
        macro: str,
        target_lib_dir:str,
        macro_definitions:List[dict]
) -> Dict[str, Any]:

    fixture_class_info_list: List[Dict[str, Any]] = []  # 存储测试夹具中的信息
    parent_class = cursor.semantic_parent

    test_case_id = cursor.semantic_parent.spelling.split("_")[0]

    for child in parent_class.get_children():
        if child.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
            test_case_id = child.referenced.spelling

    # 解析测试夹具
    for class_cursor in class_cursor_list[1:]:  # 取每个测试夹具的源码
        fixture_class_name = class_cursor.spelling
        type_def_list_in_fixture = []  # 存储测试夹具中引用的类型

        # 取其定义位置
        test_fixture_decl = {
            "file": class_cursor.location.file.name if class_cursor.location.file else "",
            "start_line": class_cursor.extent.start.line,
            "end_line": class_cursor.extent.end.line
        }

        # 初始化cxx方法列表
        cxx_method_list = []

        # 取成员函数类型
        cxx_method_type = (
            cindex.CursorKind.CXX_METHOD,
            cindex.CursorKind.FUNCTION_TEMPLATE,
            cindex.CursorKind.CONSTRUCTOR,
            cindex.CursorKind.DESTRUCTOR,
            cindex.CursorKind.CONVERSION_FUNCTION
        )

        for child in class_cursor.walk_preorder():
            # 存储在测试夹具中被使用的类型
            field_type_in_fixture = []

            # 分析成员变量
            if child.kind == cindex.CursorKind.FIELD_DECL:
                for filed_child in child.get_children():
                    if filed_child.kind == cindex.CursorKind.TYPE_REF:
                        filed_child_referenced_name = filed_child.location.file.name
                        if is_path_contained_in(target_lib_dir, filed_child_referenced_name):
                            field_type_in_fixture.append(filed_child.referenced)

            # 处理成员变量的类型定义
            for field_type_ref in field_type_in_fixture:
                field_type_def = get_type_ref_definition(field_type_ref, target_lib_dir)
                if field_type_def is not None:
                    type_def_list_in_fixture.append(field_type_def)

            # 分析成员函数
            if child.kind in cxx_method_type:

                isSrcCode = child.is_definition()

                front_2 = child.get_usr()
                back_2 = generate_unique_cursor_id(child)
                cxxmethod_id = f'{front_2} & {back_2}'

                cxx_method_info = {
                    "cxxmethod_id": cxxmethod_id,
                    "isSrcCode": isSrcCode
                }

                cxx_method_list.append(cxx_method_info)

        fixture_info = {
            "fixture_class_name": fixture_class_name,
            "fixtur_definition": test_fixture_decl,
            "cxx_method_list": cxx_method_list,
            "type_def_list_in_fixture": type_def_list_in_fixture,
        }

        fixture_class_info_list.append(fixture_info)
    front_3 = cursor.get_usr()
    back_3 =  generate_unique_cursor_id(cursor)
    # 生成测试用例并返回
    return {
        "macro": macro,
        "test_case_id":test_case_id,
        "testbody_id":f'{front_3} & {back_3}',
        "include_directives": list(include_directives),
        "macro_definition":macro_definitions,
        "fixture_class": fixture_class_info_list
    }


def get_type_ref_definition(cursor_reference: cindex.Cursor, target_lib_dir: str) -> Optional[Dict]:
    # 获取引用位置和范围
    cursor_ref_def_file = cursor_reference.location.file.name
    cursor_ref_def_start_line = cursor_reference.extent.start.line
    cursor_ref_def_end_line = cursor_reference.extent.end.line

    # 如果不在目标库目录内，直接返回 None
    if not is_path_contained_in(target_lib_dir, cursor_ref_def_file):
        return None

    type_def_info = {
        'flag': False,
        'type_def': {
            'file': cursor_ref_def_file,
            'start_line': cursor_ref_def_start_line,
            'end_line': cursor_ref_def_end_line
        }
    }

    # 处理typedef类型
    if cursor_reference.kind == cindex.CursorKind.TYPEDEF_DECL:
        typedef_type = cursor_reference.underlying_typedef_type
        typedef_decl = typedef_type.get_declaration()

        # 如果typedef和decl不是写在一起，获取底层类型的定义
        if not typedef_decl.extent == cursor_reference.extent and typedef_decl.location.file is not None:
            cursor_underlying_file = typedef_decl.location.file.name
            cursor_underlying_start_line = typedef_decl.extent.start.line
            cursor_underlying_end_line = typedef_decl.extent.end.line

            # 如果底层类型文件在目标库目录中
            if is_path_contained_in(target_lib_dir, cursor_underlying_file):
                type_def_info['flag'] = True
                type_def_info['underlying_type'] = {
                    'file': cursor_underlying_file,
                    'start_line': cursor_underlying_start_line,
                    'end_line': cursor_underlying_end_line
                }

    return type_def_info

def pack_function_definitions(cursor: cindex.Cursor, target_function_call: List[str],target_lib_dir:str) -> dict:

    target_function_called_in_this_function = set()

    type_definition_set = []
    (
        target_function_calls,
        aux_function_cursor_list,
        type_ref_list
    ) = collect_function_call_details(cursor, target_function_call, unit_test_dir, ignore_type_path, target_lib_dir)

    for type_ref in type_ref_list:
        # 填充类型定义列表
        if get_type_ref_definition(type_ref, target_lib_dir) is not None:
            type_definition_set.append(get_type_ref_definition(type_ref, target_lib_dir))

    for child in cursor.walk_preorder():

        if child.kind == cindex.CursorKind.CALL_EXPR and child.spelling in target_function_call:
            target_function_called_in_this_function.add(child.spelling)


    function_info = {
        'spelling':cursor.spelling,
        'kind': str(cursor.kind),
        'file':cursor.location.file.name,
        'start_line': cursor.extent.start.line,
        'end_line': cursor.extent.end.line,
        'target_function_called': list(target_function_called_in_this_function),
        'type_ref_list':type_definition_set
    }

    return function_info


def is_valid_cursor(referenced: cindex.Cursor, unit_test_dir: str) -> bool:
    method_type = (
        cindex.CursorKind.CXX_METHOD,
        cindex.CursorKind.FUNCTION_TEMPLATE,
        cindex.CursorKind.CONSTRUCTOR,
        cindex.CursorKind.DESTRUCTOR,
        cindex.CursorKind.CONVERSION_FUNCTION,
        cindex.CursorKind.FUNCTION_DECL
    )
    if not referenced or not referenced.location or not referenced.location.file:
        return False
    if referenced.kind not in method_type:
        return False
    return is_path_contained_in(unit_test_dir, referenced.location.file.name)


def is_valid_type_ref(referenced: cindex.Cursor) -> bool:
    if not referenced or not referenced.location or not referenced.location.file:
        return False
    return True


def collect_function_call_details(
        testBody: cindex.Cursor,
        target_function_call: List,
        unit_test_dir: str,
        ignore_type_path: List,
        target_lib_dir: str) -> Tuple[List[str], List[cindex.Cursor], List[cindex.Cursor]]:
    if not testBody or not target_function_call:
        return [], [], []

    target_function_set = set()
    aux_function_cursors = []
    target_function_call_in_testbody = []
    type_ref_list = set()

    for cursor in testBody.walk_preorder():
        if cursor.kind == cindex.CursorKind.CALL_EXPR:
            # 处理目标函数调用
            if cursor.spelling in target_function_call and cursor.spelling not in target_function_set:
                target_function_call_in_testbody.append(cursor.spelling)
                target_function_set.add(cursor.spelling)
            # 处理非目标函数调用，检查是否为辅助函数
            elif cursor.spelling not in target_function_call:
                referenced = cursor.referenced
                if referenced and is_valid_cursor(referenced, unit_test_dir):
                    aux_function_cursors.append(referenced)

        elif cursor.kind == cindex.CursorKind.TYPE_REF:
            referenced = cursor.referenced
            if referenced:
                ref_loc = referenced.location.file.name
                ref_spelling = referenced.spelling
                # 处理类型引用
                if (is_valid_type_ref(referenced) and
                        not is_path_contained_in_any(ignore_type_path, ref_loc) and
                        not ref_spelling.endswith("_Test") and
                        is_path_contained_in(target_lib_dir, ref_loc)):
                    type_ref_list.add(referenced)
    return target_function_call_in_testbody, aux_function_cursors, list(type_ref_list)


def get_final_gtest_base_class(
    class_cursor: cindex.Cursor,
    root_cursor: cindex.Cursor,
    class_def_list: List,
    ignore_type_path: List,
    checked_classes=None,
    class_cursor_list=None,
) -> Tuple[str, List[cindex.Cursor]]:

    # 初始化默认值
    checked_classes = checked_classes or set()
    class_cursor_list = class_cursor_list or []

    # 检查当前类的文件是否在忽略路径中
    class_file = class_cursor.location.file
    #print(class_cursor.spelling,"==>",class_cursor.kind,"==>",class_file)
    if class_file and not is_path_contained_in_any(ignore_type_path, class_file.name):
        class_cursor_list.append(class_cursor)  # 保存当前类的 cursor

    # 初始返回值和基类列表
    base_class_list = []
    result_final = 'None'

    # 确保输入是类声明
    if class_cursor.kind not in [cindex.CursorKind.CLASS_DECL, cindex.CursorKind.CLASS_TEMPLATE]:
    #if class_cursor.kind not in [cindex.CursorKind.CLASS_DECL]:
        return result_final, class_cursor_list
    # 防止循环继承导致的无限递归
    class_usr = class_cursor.get_usr()
    if class_usr in checked_classes:
        return result_final, class_cursor_list
    checked_classes.add(class_usr)

    # 查找当前类的所有基类
    for class_def in class_def_list:
        if class_def.spelling == class_cursor.spelling:
            base_class_list.append(class_def)
            break
    # 遍历基类，递归查找最终基类
    for base_cursor in base_class_list:
        for base in base_cursor.get_children():
            if base.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
                base_type = base.type.get_canonical()
                base_decl = base_type.get_declaration()
                base_usr = base_decl.get_usr()
                # 检查基类是否为 GTest 类型
                if base_usr == 'c:@N@testing@S@Test':
                    result_final = 'Test'
                elif base_usr.startswith('c:@N@testing@ST>1#T@TestWithParam') or base_usr.startswith('c:@N@testing@ST>1#T@WithParamInterface'):
                    result_final = 'TestWithParam'
                else:
                    # 递归检查基类
                    result, _ = get_final_gtest_base_class(
                        base_decl, root_cursor, class_def_list, ignore_type_path, checked_classes, class_cursor_list
                    )
                    if result != 'None':
                        result_final = result

    return result_final, class_cursor_list



def is_derived_from_testing_test(class_cursor: cindex.Cursor) -> bool:
    """
    检查给定的类是否派生自 ::testing::Test。

    :param class_cursor: 类的游标对象
    :return: 如果类派生自 ::testing::Test，则返回 True，否则返回 False
    """

    # 确保输入不为空
    if not class_cursor:
        return False

    # 确保输入是类声明或类模板
    if class_cursor.kind not in [cindex.CursorKind.CLASS_DECL, cindex.CursorKind.CLASS_TEMPLATE]:
    #if class_cursor.kind not in [cindex.CursorKind.CLASS_DECL]:
        return False

    # 遍历基类
    for base_class in class_cursor.get_children():

        if base_class.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:

            try:
                # 获取基类类型
                base_type = base_class.type
                # 获取基类声明
                base_declaration = base_type.get_declaration()
                # 获取基类的完全限定名
                base_qualified_name = base_declaration.get_usr()
                # 检查是否为 ::testing::Test
                if base_qualified_name == 'c:@N@testing@S@Test':
                    return True
            except Exception as e:
                # 处理异常，返回 False
                print(f"Error occurred: {e}")
                return False

    return False


def parse_source_file_and_get_cursor(cmd: cindex.CompileCommand) -> Tuple[cindex.Cursor, str]:
    src_file = cmd.filename  # 获取源文件路径

    # 检查文件是否存在
    if not os.path.exists(src_file):
        raise FileNotFoundError(f"Source file {src_file} does not exist.")

    # 处理编译参数
    compile_args = process_compile_args(cmd)

    # 创建索引对象
    index = cindex.Index.create()

    try:
        # 解析源文件，生成 TranslationUnit
        tu = index.parse(
            src_file,
            args=compile_args,
            options=cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
        )
    except cindex.TranslationUnitLoadError as e:
        raise RuntimeError(f"Failed to parse source file {src_file}: {e}")
    finally:
        # 释放索引对象资源
        del index

    return tu.cursor, src_file


def process_cursor(
    cursor: Cursor,
    root_cursor: Cursor,
    src_file: str,
    method_definitions: Dict,
    test_case_info_file: List[dict],
    include_directives:Set[str],
    class_cursor_list: List[Cursor],
    call_graph_all: Dict[str, List[str]],
    unit_test_dir: str,
    target_function_call: List[str],
    ignore_type_path: List[str],
    ignore_header_path: List[str],
    target_lib_dir:str,
    var_infos:Dict,
    class_infos:Dict,
    evalgen_infos:Dict,
    testcase_to_evalgen:Dict,
    macro_definitions:list[dict]
) -> None:

    """
    递归地处理游标及其子游标，针对 namespace 和 class 进行深入遍历
    """
    # 处理类声明或模板
    if cursor.kind in [cindex.CursorKind.CLASS_DECL, cindex.CursorKind.CLASS_TEMPLATE]:
        class_cursor_list.append(cursor)

    method_type = (
        cindex.CursorKind.CXX_METHOD,
        cindex.CursorKind.FUNCTION_TEMPLATE,
        cindex.CursorKind.CONSTRUCTOR,
        cindex.CursorKind.DESTRUCTOR,
        cindex.CursorKind.CONVERSION_FUNCTION,
        cindex.CursorKind.FUNCTION_DECL
    )

    # 处理函数定义
    if (
        cursor.kind in method_type and
        cursor.is_definition() and
        (cursor.location.file.name == src_file or
         (is_path_contained_in(unit_test_dir, cursor.location.file.name) and os.path.splitext(cursor.location.file.name)[1] in [".h",".hpp"]))
    ):
        method_definition_detail = pack_function_definitions(cursor, target_function_call,target_lib_dir)

        #cxx_id—— = cursor.get_usr()
        front_4 = cursor.get_usr()
        back_4 = generate_unique_cursor_id(cursor)

        cxx_id = f'{front_4} & {back_4}'
        method_definitions[cxx_id] = method_definition_detail

        called_list = get_function_call_graph(cursor, unit_test_dir)

        call_graph_all[cxx_id] = called_list

    if cursor.spelling.startswith("gtest_") and cursor.spelling.endswith("_EvalGenerator_") and cursor.kind == cindex.CursorKind.FUNCTION_DECL:
        target_function_call_in_evalgen = set()
        var_ref_in_evalgen = set()
        evalgen_file = cursor.location.file.name
        evalgen_start_line = cursor.extent.start.line
        evalgen_end_line = cursor.extent.end.line

        for child in cursor.walk_preorder():
            child_ref = child.referenced
            if child_ref and child.kind == cindex.CursorKind.DECL_REF_EXPR and not is_path_contained_in_any(ignore_type_path, child_ref.location.file.name) and is_path_contained_in(target_lib_dir, child_ref.location.file.name):

                #print(child.spelling, "==>", child_ref.kind, "==>", child_ref.location)
                if child_ref.kind == cindex.CursorKind.FUNCTION_DECL and child_ref.spelling in target_function_call:
                    target_function_call_in_evalgen.add(child_ref.spelling)
                elif child_ref.kind == cindex.CursorKind.VAR_DECL and is_path_contained_in(unit_test_dir, child_ref.location.file.name):
                    var_id = child_ref.get_usr()
                    var_ref_in_evalgen.add(var_id)

        front_8 = cursor.get_usr()
        back_8 = generate_unique_cursor_id(cursor)
        evalgen_id= f'{front_8} & {back_8}'
        evalgen_info = {
            'function_name': cursor.spelling,
            'file':evalgen_file,
            'start_line': evalgen_start_line,
            'end_line': evalgen_end_line,
            'target_function_call': list(target_function_call_in_evalgen),
            'var_ref': list(var_ref_in_evalgen),
        }
        evalgen_infos[evalgen_id] = evalgen_info

    if cursor.spelling.startswith("gtest_") and cursor.spelling.endswith("_dummy_") and cursor.kind == cindex.CursorKind.VAR_DECL and cursor.spelling != "gtest_registering_dummy_":
        for child in cursor.walk_preorder():
            if child.kind == cindex.CursorKind.CALL_EXPR and child.spelling == "GetTestSuitePatternHolder":
                for child_child in child.walk_preorder():
                    if child_child.kind == cindex.CursorKind.STRING_LITERAL and "." not in child_child.spelling:
                        test_case_name = child_child.spelling.replace('"', '')

            elif child.kind == cindex.CursorKind.CALL_EXPR and child.spelling == "AddTestSuiteInstantiation":
                for child_child in child.walk_preorder():
                    if child_child.kind == cindex.CursorKind.DECL_REF_EXPR and (child_child.spelling.startswith("gtest_") and child_child.spelling.endswith("_EvalGenerator_")):

                        front_9 = child_child.referenced.get_usr()
                        back_9 = generate_unique_cursor_id(child_child.referenced)
                        eval_generator_id = f'{front_9} & {back_9}'


        if test_case_name and eval_generator_id:
            if test_case_name not in testcase_to_evalgen:
                value = []
                value.append(eval_generator_id)
                testcase_to_evalgen[test_case_name] = value
            else:
                testcase_to_evalgen[test_case_name].append(eval_generator_id)


    #解析变量，因为其可能传入参数生成器
    if (cursor.kind == cindex.CursorKind.VAR_DECL and not (cursor.spelling.startswith("gtest_") and cursor.spelling.endswith("_dummy_")) and
             is_path_contained_in(unit_test_dir, cursor.location.file.name)):
        var_info = get_var_info(cursor,src_file,target_function_call,method_type,unit_test_dir,target_lib_dir)
        var_id = cursor.get_usr()
        var_infos[var_id]=var_info

    # 解析类，因为其可能会被参数生成器使用
    if cursor.kind in (cindex.CursorKind.CLASS_DECL, cindex.CursorKind.CLASS_TEMPLATE):

        class_referenced = cursor.referenced
        if class_referenced and is_path_contained_in(unit_test_dir,class_referenced.location.file.name):
            class_info = analyze_class(class_referenced,target_lib_dir)
            front_9 = class_referenced.get_usr()
            back_9 = generate_unique_cursor_id(class_referenced)
            class_id = f'{front_9} & {back_9}'
            class_infos[class_id] = class_info

    if cursor.kind == cindex.CursorKind.MACRO_DEFINITION and cursor.location.file and is_path_contained_in(unit_test_dir,cursor.location.file.name):
        file = cursor.location.file.name
        start_line = cursor.extent.start.line
        end_line = cursor.extent.end.line
        if start_line != end_line:
            macro_info = {
                'file': file,
                'start_line': start_line,
                'end_line': end_line
            }
            macro_definitions.append(macro_info)

    # 取引入的头文件
    if cursor.kind == cindex.CursorKind.INCLUSION_DIRECTIVE and is_path_contained_in(unit_test_dir, cursor.location.file.name):
        include_file = cursor.get_included_file().name
        if not is_path_contained_in_any(ignore_header_path, include_file):
            include_directives.add(include_file)

    # 处理 TestBody
    if cursor.spelling == "TestBody" and cursor.semantic_parent.kind == cindex.CursorKind.CLASS_DECL and cursor.is_definition():
        parent_class = cursor.semantic_parent

        final_base_class, class_cursor_list = get_final_gtest_base_class(
            parent_class, root_cursor, class_cursor_list, ignore_type_path
        )

        if is_derived_from_testing_test(parent_class):  # 判断是否直接继承自 ::testing::TEST

            front_5 = cursor.get_usr()
            back_5 = generate_unique_cursor_id(cursor)
            test_case_info_file.append({
                "macro": "TEST",
                "include_directives": list(include_directives),
                "macro_definition":list(macro_definitions),
                "testbody_id": f'{front_5} & {back_5}'
            })
        elif final_base_class in {"Test", "TestWithParam"}:  # 处理 TEST_F 和 TEST_P
            macro = "TEST_F" if final_base_class == "Test" else "TEST_P"

            test_case = analyze_test_p_macro(
                cursor=cursor,
                class_cursor_list=class_cursor_list,
                include_directives=include_directives,
                macro=macro,
                target_lib_dir=target_lib_dir,
                macro_definitions = macro_definitions
            )
            test_case_info_file.append(test_case)

    struct_type = {
        cindex.CursorKind.STRUCT_DECL,
        cindex.CursorKind.CLASS_DECL,
        cindex.CursorKind.CLASS_TEMPLATE,
        cindex.CursorKind.NAMESPACE,
        cindex.CursorKind.UNION_DECL
    }
    # 如果是 namespace 或 class，则递归遍历其子节点
    if cursor.kind in struct_type:
        for child in cursor.get_children():
            process_cursor(
                cursor=child,
                root_cursor=root_cursor,
                src_file=src_file,
                method_definitions=method_definitions,
                test_case_info_file=test_case_info_file,
                include_directives=include_directives,
                class_cursor_list=class_cursor_list,
                call_graph_all=call_graph_all,
                unit_test_dir=unit_test_dir,
                target_function_call=target_function_call,
                ignore_type_path=ignore_type_path,
                ignore_header_path=ignore_header_path,
                target_lib_dir=target_lib_dir,
                var_infos=var_infos,
                class_infos=class_infos,
                evalgen_infos=evalgen_infos,
                testcase_to_evalgen=testcase_to_evalgen,
                macro_definitions=macro_definitions
            )

def main(
    compile_cmd_dir: str,
    target_function_call: List[str],
    unit_test_dir: str,
    ignore_type_path: List[str],
    ignore_header_path: List[str],
    target_lib_dir: str
) -> None:
    compile_cmd = load_compile_commands(compile_cmd_dir)

    for cmd in tqdm(compile_cmd, desc="Parsing unit test code", unit="cmd"):


        # 初始化数据结构
        call_graph_all = {}
        method_definitions = {}
        test_case_info_file = []
        include_directives = set()
        macro_definitions = []
        var_infos = {}
        class_infos = {}
        evalgen_infos = {}
        testcase_to_evalgen = {}

        # 获取单元测试的 AST 根游标和源文件路径
        root_cursor, src_file = parse_source_file_and_get_cursor(cmd)
        #print("*" * 40,os.path.basename(src_file),"*" * 40)
        # 判断是否为单元测试文件，不在指定目录则跳过
        if not is_path_contained_in(unit_test_dir, src_file):
            continue

        # 初始化辅助列表
        class_cursor_list = []

        # 遍历根游标的直接子节点，处理游标
        for cursor in root_cursor.get_children():
            process_cursor(
                cursor=cursor,
                root_cursor=root_cursor,
                src_file=src_file,
                method_definitions=method_definitions,
                test_case_info_file=test_case_info_file,
                include_directives=include_directives,
                class_cursor_list=class_cursor_list,
                call_graph_all=call_graph_all,
                unit_test_dir=unit_test_dir,
                target_function_call=target_function_call,
                ignore_type_path=ignore_type_path,
                ignore_header_path=ignore_header_path,
                target_lib_dir=target_lib_dir,
                var_infos=var_infos,
                class_infos=class_infos,
                evalgen_infos=evalgen_infos,
                testcase_to_evalgen=testcase_to_evalgen,
                macro_definitions = macro_definitions
            )


        test_case_info_all = {src_file: test_case_info_file}
        #写入结果文件
        write_dict_to_json_in_dir(call_graph_all, unit_test_dir, 'call_graph_all.json')
        write_dict_to_json_in_dir(method_definitions, unit_test_dir, 'method_definitions.json')
        write_dict_to_json_in_dir(test_case_info_all, unit_test_dir, 'testCase_info.json')
        write_dict_to_json_in_dir(var_infos, unit_test_dir, 'var_infos.json')
        write_dict_to_json_in_dir(class_infos, unit_test_dir, 'class_infos.json')
        write_dict_to_json_in_dir(evalgen_infos, unit_test_dir, 'evalgen_infos.json')
        write_dict_to_json_in_dir(testcase_to_evalgen, unit_test_dir, 'testcase_to_evalgen.json')

# 主程序入口
if __name__ == '__main__':

    target_lib_dir = '/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom'

    compile_cmd_dir = '/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/build'
    unit_test_dir = '/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test'
    target_function_call = load_public_api('/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/build')

    #指定忽略类型提取路径
    ignore_type_path = ['/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/third_party','/usr/']

    #指定忽略头文件提取路径
    ignore_header_path = ['/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/third_party','/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test']

    # 打印提取的每个单元测试文件中的 API 调用
    main(compile_cmd_dir,target_function_call,unit_test_dir,ignore_type_path,ignore_header_path,target_lib_dir)
