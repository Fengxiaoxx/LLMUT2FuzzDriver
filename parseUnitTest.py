from utils import load_compile_commands, load_public_api, process_compile_args, is_path_contained_in, write_dict_to_json_in_dir, is_path_contained_in_any
from clang.cindex import Cursor
from clang import cindex  # 导入 Clang 的 Python 接口模块
from typing import List, Tuple, Optional, Dict, Any, Set
import os
from tqdm import tqdm

# 设置 Clang 库的路径
cindex.Config.set_library_file('/usr/lib/llvm-15/lib/libclang.so.1')


def get_function_call_graph(cursor: cindex.Cursor, unit_test_dir: str) -> List[str]:

    called_function_list = set()

    if cursor.is_definition():
        for child in cursor.walk_preorder():
            # 检查当前节点是否是函数调用
            if child.kind == cindex.CursorKind.CALL_EXPR and child.spelling != cursor.spelling: #防止递归调用
                referenced = child.referenced
                if referenced is not None and referenced.location.file is not None:
                    try:
                        referenced_path = referenced.location.file.name
                        # 检查路径是否在指定目录中
                        if is_path_contained_in(unit_test_dir, referenced_path):
                            called_function_name = referenced.spelling
                            # 检查是否有定义
                            definition = referenced.get_definition()
                            if definition is not None and definition.location.file is not None:
                                called_function_def_file = definition.location.file.name
                                file_without_extension = os.path.splitext(called_function_def_file)[0]
                                # 拼接函数标识符
                                function_identifier = f"{file_without_extension} | {called_function_name}"
                                called_function_list.add(function_identifier) #去重
                    except AttributeError as e:
                        # 捕获可能的异常，例如引用或定义的属性不存在
                        print(f"AttributeError encountered: {e}")
                    except Exception as e:
                        # 捕获其他异常并打印日志以供调试
                        print(f"Unexpected error encountered: {e}")

    return list(called_function_list)


def analyze_test_p_macro(
        cursor: cindex.Cursor,
        class_cursor_list: List[cindex.Cursor],
        target_function_call: Dict[str, Any],
        unit_test_dir: str,
        ignore_type_path: List[str],
        testBody_definition_info: Dict[str, Any],
        include_directives: Set[str],
        macro: str
) -> Dict[str, Any]:

    fixture_class_info_list: List[Dict[str, Any]] = []  # 存储测试夹具中的信息

    # 解析 testbody
    testbody: Dict[str, Any] = build_testbody(
        cursor=cursor,
        target_function_call=target_function_call,
        unit_test_dir=unit_test_dir,
        ignore_type_path=ignore_type_path,
        testBody_definition_info=testBody_definition_info,
        target_lib_dir=target_lib_dir
    )

    # 解析测试夹具
    for class_cursor in class_cursor_list[1:]:  # 取每个测试夹具的源码
        fixture_class_name: str = class_cursor.spelling
        cxx_method_not_def_in_class: List[Dict[str, Any]] = []  # 用来存储类中没有定义的成员函数
        type_def_list_in_fixture: List[Dict[str, Any]] = []  # 存储测试夹具中引用的类型

        # 取其定义位置
        test_fixture_decl: Dict[str, Any] = {
            "file": class_cursor.location.file.name if class_cursor.location.file else "",
            "start_line": class_cursor.extent.start.line,
            "end_line": class_cursor.extent.end.line
        }

        # Initialize cxxmethod_info_list before the loop
        cxxmethod_info_list: List[Dict[str, Any]] = []

        # 取成员函数
        cxx_method_type = (
            cindex.CursorKind.CXX_METHOD,
            cindex.CursorKind.FUNCTION_TEMPLATE,
            cindex.CursorKind.CONSTRUCTOR,
            cindex.CursorKind.DESTRUCTOR
        )

        for child in class_cursor.walk_preorder():
            field_type_in_fixture: List[cindex.Type] = []  # 存储在测试夹具中被使用的类型

            # 分析成员变量
            if child.kind == cindex.CursorKind.FIELD_DECL:
                for filed_child in child.get_children():
                    if filed_child.kind == cindex.CursorKind.TYPE_REF:
                        filed_child_referenced_name = filed_child.location.file.name
                        if is_path_contained_in(target_lib_dir,filed_child_referenced_name):
                            field_type_in_fixture.append(filed_child.referenced)

            for field_type_ref in field_type_in_fixture:
                field_type_def = get_type_ref_definition(field_type_ref,target_lib_dir)
                type_def_list_in_fixture.append(field_type_def)

            # 分析成员函数
            if child.kind in cxx_method_type:
                # 成员函数名
                cxxmethod_name: str = child.spelling
                # Remove this line
                # cxxmethod_info_list: List[Dict[str, Any]] = []
                if not child.is_definition():
                    # 获取定义
                    child_definition: Optional[cindex.Cursor] = child.get_definition()

                    if child_definition is not None:
                        # 定义在当前文件
                        cxx_method_definition_info: Dict[str, Any] = {
                            "isSrcCode": True,
                            "file": child_definition.location.file.name if child_definition.location.file else "",
                            "start_line": child_definition.extent.start.line,
                            "end_line": child_definition.extent.end.line
                        }
                    else:
                        # 获取引用
                        child_reference: Optional[cindex.Cursor] = child.referenced
                        if child_reference is not None:
                            cxx_method_definition_info = {
                                "isSrcCode": child_reference.is_definition(),
                                "file": child_reference.location.file.name if child_reference.location.file else "",
                                "start_line": child_reference.extent.start.line,
                                "end_line": child_reference.extent.end.line
                            }
                        else:
                            # 如果引用也不存在，不记录
                            cxx_method_definition_info = None

                    if cxx_method_definition_info:
                        cxx_method_not_def_in_class.append(cxx_method_definition_info)

                # 如果 child 是定义，提取函数调用信息
                else:
                    cxxmethod_info: Dict[str, Any] = build_cxxmethod(
                        cursor=cursor,
                        target_function_call=target_function_call,
                        unit_test_dir=unit_test_dir,
                        ignore_type_path=ignore_type_path,
                        cxxmethod_name=cxxmethod_name
                    )
                    cxxmethod_info_list.append(cxxmethod_info)

        fixture_info: Dict[str, Any] = {
            "fixture_class_name": fixture_class_name,
            "fixtur_definition": test_fixture_decl,
            "cxx_method_not_def_in_class": cxx_method_not_def_in_class,
            "aux_function_in_cxxmethod": cxxmethod_info_list,
            "type_def_list_in_fixture": type_def_list_in_fixture,
        }
        fixture_class_info_list.append(fixture_info)

    # 生成键名并存储数据
    test_case: Dict[str, Any] = {
        "macro": macro,
        "include_directives": list(include_directives),
        "testbody": testbody,  # 使用提前定义的 testbody
        "fixture_class": fixture_class_info_list
    }

    return test_case



def build_cxxmethod(
    cursor: Cursor,
    target_function_call: List[str],
    unit_test_dir: str,
    ignore_type_path: List[str],
    cxxmethod_name: str
) -> Dict[str, Any]:

    # 初始化辅助函数和类型定义列表
    aux_function_definition_list: List[Dict[str, Any]] = []
    type_definition_list: List[Dict[str, Any]] = []

    # 获取目标函数调用、自定义辅助函数及类型引用
    target_function_calls: List[Dict[str, Any]]
    aux_function_cursor_list: List[Cursor]
    type_ref_list: List[Cursor]

    (
        target_function_calls,
        aux_function_cursor_list,
        type_ref_list
    ) = collect_function_call_details(cursor, target_function_call, unit_test_dir, ignore_type_path,target_lib_dir)

    # 填充辅助函数定义列表
    for aux_function_cursor in aux_function_cursor_list:
        aux_function_definition_list.append(get_aux_function_definition(aux_function_cursor))

    # 填充类型定义列表
    for type_ref in type_ref_list:
        type_definition_list.append(get_type_ref_definition(type_ref,target_lib_dir))

    # 构造 testbody 字典
    return {
        "cxxmethod_name":cxxmethod_name,
        "aux_function_definition_list": aux_function_definition_list,
        "type_definition_list": type_definition_list,
        "target_function_called": target_function_calls,
    }


def build_testbody(
    cursor: Cursor,
    target_function_call: List[str],
    unit_test_dir: str,
    ignore_type_path: List[str],
    testBody_definition_info: Dict[str, Any],
    target_lib_dir:str
) -> Dict[str, Any]:

    # 初始化辅助函数和类型定义列表
    aux_function_definition_list: List[Dict[str, Any]] = []
    type_definition_list: List[Dict[str, Any]] = []

    # 获取目标函数调用、自定义辅助函数及类型引用
    target_function_calls: List[Dict[str, Any]]
    aux_function_cursor_list: List[Cursor]
    type_ref_list: List[Cursor]

    (
        target_function_calls,
        aux_function_cursor_list,
        type_ref_list
    ) = collect_function_call_details(cursor, target_function_call, unit_test_dir, ignore_type_path,target_lib_dir)

    # 填充辅助函数定义列表
    for aux_function_cursor in aux_function_cursor_list:
        aux_function_definition_list.append(get_aux_function_definition(aux_function_cursor))

    # 填充类型定义列表
    for type_ref in type_ref_list:
        type_definition_list.append(get_type_ref_definition(type_ref,target_lib_dir))

    # 构造 testbody 字典
    return {
        "testBody_definition_info": testBody_definition_info,
        "aux_function_definition_list": aux_function_definition_list,
        "type_definition_list": type_definition_list,
        "target_function_called": target_function_calls,
    }


def get_type_ref_definition(cursor_reference: cindex.Cursor,target_lib_dir:str) -> Optional[Dict]:

    cursor_ref_def_file = cursor_reference.location.file.name
    cursor_ref_def_start_line = cursor_reference.extent.start.line
    cursor_ref_def_end_line = cursor_reference.extent.end.line
    if is_path_contained_in(target_lib_dir, cursor_ref_def_file):
        if cursor_reference.kind == cindex.CursorKind.TYPEDEF_DECL:
            # 获取 typedef 声明对应的类型声明
            typedef_type = cursor_reference.underlying_typedef_type
            typedef_decl = typedef_type.get_declaration()

            #借助extent来区分typedef和decl是不是写在一起了
            if not typedef_decl.extent == cursor_reference.extent and typedef_decl.location.file is not None:

                cursor_underlying_file = typedef_decl.location.file.name
                cursor_underlying_start_line = typedef_decl.extent.start.line
                cursor_underlying_end_line = typedef_decl.extent.end.line

                if is_path_contained_in(target_lib_dir,cursor_underlying_file):
                #flag用来标记两种类型：True：具有底层type；False：定义和typedef在一起
                    type_def_info = {
                        'flag': True,
                        'type_def':{
                            'file': cursor_ref_def_file,
                            'start_line': cursor_ref_def_start_line,
                            'end_line': cursor_ref_def_end_line,
                            },
                        'underlying_type':{
                            'file': cursor_underlying_file,
                            'start_line': cursor_underlying_start_line,
                            'end_line': cursor_underlying_end_line,
                        }
                    }
                else:
                    type_def_info = {
                        'flag': False,
                        'type_def':{
                            'file': cursor_ref_def_file,
                            'start_line': cursor_ref_def_start_line,
                            'end_line': cursor_ref_def_end_line,
                            }
                    }
            else:
                type_def_info = {
                    'flag': False,
                    'type_def':{
                        'file': cursor_ref_def_file,
                        'start_line': cursor_ref_def_start_line,
                        'end_line': cursor_ref_def_end_line,
                        }
                }
        else:
            type_def_info = {
                'flag': False,
                'type_def': {
                    'file': cursor_ref_def_file,
                    'start_line': cursor_ref_def_start_line,
                    'end_line': cursor_ref_def_end_line,
                }
            }
        return type_def_info
    else:
        return None


def get_aux_function_definition(cursor_reference: cindex.Cursor) -> Optional[Dict[str, Any]]:
    if cursor_reference is None:
        return None

    try:
        isSrcCode = cursor_reference.is_definition()

        if cursor_reference.location.file and cursor_reference.extent:
            if isSrcCode:
                aux_function_info = {
                    'file': cursor_reference.location.file.name,
                    "aux_function_name": cursor_reference.spelling,
                    'start_line': cursor_reference.extent.start.line,
                    'end_line': cursor_reference.extent.end.line,
                    'isSrcCode': isSrcCode
                }
            else:
                aux_function_info = {
                    'file': cursor_reference.location.file.name,
                    "aux_function_name": cursor_reference.spelling,
                    'isSrcCode': isSrcCode
                }
            return aux_function_info
        else:
            return None
    except AttributeError as e:
        print(f"Error: {e}")
        return None


def pack_function_definitions(cursor: cindex.Cursor) -> dict:
    if not isinstance(cursor, cindex.Cursor):
        raise TypeError("Expected cindex.Cursor, got {}".format(type(cursor).__name__))

    if not cursor:
        raise ValueError("Cursor is invalid or None")

    if not cursor.extent:
        raise ValueError("Cursor extent is invalid or None")

    function_info = {
        'spelling': cursor.spelling,
        'kind': str(cursor.kind),
        'start_line': cursor.extent.start.line,
        'end_line': cursor.extent.end.line
    }
    return function_info


def is_valid_cursor(referenced: cindex.Cursor, unit_test_dir: str) -> bool:
    if not referenced or not referenced.location or not referenced.location.file:
        return False
    if referenced.kind not in (cindex.CursorKind.CXX_METHOD, cindex.CursorKind.FUNCTION_DECL):
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
        ignore_type_path:List,
        target_lib_dir:str) -> Tuple[List[str], List[cindex.Cursor], List[cindex.Cursor]]:
    if not testBody or not target_function_call:
        return [], [], []

    target_function_set = set()  # 使用集合来跟踪已添加的元素，确保唯一性
    aux_function_cursors = []  # 用来存放那些由开发者定义在单元测试项目中的辅助函数的cursor
    target_function_call_in_testbody = []
    type_ref_list = set()

    try:
        for cursor in testBody.walk_preorder():
            if cursor.kind == cindex.CursorKind.CALL_EXPR:
                if cursor.spelling in target_function_call:
                    if cursor.spelling not in target_function_set:
                        target_function_call_in_testbody.append(cursor.spelling)
                        target_function_set.add(cursor.spelling)
                else:
                    referenced = cursor.referenced
                    if is_valid_cursor(referenced, unit_test_dir):
                        aux_function_cursors.append(referenced)

            elif cursor.kind == cindex.CursorKind.TYPE_REF:
                referenced = cursor.referenced
                ref_loc = referenced.location.file.name
                ref_spelling = referenced.spelling
                if (
                        is_valid_type_ref(referenced)
                        and not is_path_contained_in_any(ignore_type_path, ref_loc)
                        and not ref_spelling.endswith("_Test")
                        and is_path_contained_in(target_lib_dir, ref_loc)
                ):
                    type_ref_list.add(referenced)


    except Exception as e:
        print(f"Error occurred: {e}")
        return [], [], []

    return target_function_call_in_testbody, aux_function_cursors, list(type_ref_list)



def get_final_gtest_base_class(
    class_cursor: cindex.Cursor,
    root_cursor: cindex.Cursor,
    class_def_list: List,
    checked_classes=None,
    class_cursor_list=None,
) -> Tuple[str, List[cindex.Cursor]]:

    if checked_classes is None:
        checked_classes = set()

    if class_cursor_list is None:
        class_cursor_list = []  # 在初始调用时创建新的列表

    class_cursor_list.append(class_cursor)  # 保存当前类的 cursor

    base_class_list = []
    result_final = 'None'

    # 确保输入是类声明
    if class_cursor.kind not in [cindex.CursorKind.CLASS_DECL, cindex.CursorKind.CLASS_TEMPLATE]:
        return 'None', class_cursor_list

    # 防止循环继承导致的无限递归
    class_usr = class_cursor.get_usr()
    if class_usr in checked_classes:
        return 'None', class_cursor_list
    checked_classes.add(class_usr)

    # 查找当前类的所有基类
    for class_def in class_def_list:
        if class_def.spelling == class_cursor.spelling:
            base_class_list.append(class_def)
            break

    # 遍历基类的子节点
    for base_cursor in base_class_list:
        for base in base_cursor.get_children():
            if base.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
                base_type = base.type
                base_decl = base_type.get_declaration()
                base_usr = base_decl.get_usr()

                if base_usr == 'c:@N@testing@S@Test':
                    result_final = 'Test'
                elif base_usr.startswith('c:@N@testing@ST>1#T@TestWithParam'):
                    result_final = 'TestWithParam'
                else:
                    # 递归检查基类，显式传递 class_cursor_list
                    result, _ = get_final_gtest_base_class(
                        base_decl, root_cursor, class_def_list, checked_classes, class_cursor_list
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
    method_definitions: List[dict],
    test_case_info_file: List[dict],
    include_directives: Set[str],
    class_cursor_list: List[Cursor],
    call_graph_all: Dict[str, List[str]],
    unit_test_dir: str,
    target_function_call: List[str],
    ignore_type_path: List[str],
    ignore_header_path: List[str],
    target_lib_dir: str
) -> None:
    """
    递归地处理游标及其子游标，针对 namespace 和 class 进行深入遍历
    """
    # 用来辅助查找基类
    if cursor.kind in [cindex.CursorKind.CLASS_DECL, cindex.CursorKind.CLASS_TEMPLATE]:
        class_cursor_list.append(cursor)

    # 处理函数定义（非 TestBody）
    if (
        cursor.kind in (cindex.CursorKind.FUNCTION_DECL, cindex.CursorKind.CXX_METHOD, cindex.CursorKind.FUNCTION_TEMPLATE) and
        cursor.is_definition() and
        cursor.location.file.name == src_file and
        cursor.spelling != "TestBody"
    ):
        method_definition_detail = pack_function_definitions(cursor)
        method_definitions.append(method_definition_detail)

        function_name = cursor.spelling
        function_file_without_extension = os.path.splitext(src_file)[0]
        function_identifier = f"{function_file_without_extension} | {function_name}"
        called_list = get_function_call_graph(cursor, unit_test_dir)
        call_graph_all[function_identifier] = called_list  # 确保 call_graph_all 已经作为参数传入

    # 取引入的头文件
    if cursor.kind == cindex.CursorKind.INCLUSION_DIRECTIVE and is_path_contained_in(unit_test_dir, cursor.location.file.name):
        include_file = cursor.get_included_file().name
        if not is_path_contained_in_any(ignore_header_path, include_file):
            include_directives.add(cursor.spelling)

    # 处理 TestBody
    parent_class = cursor.semantic_parent
    if cursor.spelling == "TestBody" and parent_class.kind == cindex.CursorKind.CLASS_DECL and cursor.is_definition():

        # 取本方法定义位置
        testBody_file = cursor.location.file.name
        testBody_start_line = cursor.extent.start.line
        testBody_end_line = cursor.extent.end.line

        testBody_definition_info = {
            "file": testBody_file,
            "start_line": testBody_start_line,
            "end_line": testBody_end_line
        }

        # 获取最终基类及其链表
        final_base_class, class_cursor_list = get_final_gtest_base_class(parent_class, root_cursor, class_cursor_list)

        # 对 TEST 宏进行分析
        if is_derived_from_testing_test(parent_class):  # 判断是否直接继承自 ::testing::TEST
            testbody = build_testbody(
                cursor=cursor,
                target_function_call=target_function_call,
                unit_test_dir=unit_test_dir,
                ignore_type_path=ignore_type_path,
                testBody_definition_info=testBody_definition_info,
                target_lib_dir=target_lib_dir
            )

            test_case = {
                "macro": "TEST",
                "include_directives": list(include_directives),
                "testbody": testbody,  # 使用提前定义的 testbody
            }

            test_case_info_file.append(test_case)

        else:
            if final_base_class == "Test":  # 说明是 TEST_F 宏
                macro = "TEST_F"
                test_case = analyze_test_p_macro(
                    cursor=cursor,
                    class_cursor_list=class_cursor_list,
                    target_function_call=target_function_call,
                    unit_test_dir=unit_test_dir,
                    ignore_type_path=ignore_type_path,
                    testBody_definition_info=testBody_definition_info,
                    include_directives=include_directives,
                    macro=macro
                )
                test_case_info_file.append(test_case)

            elif final_base_class == "TestWithParam":  # 说明是 TEST_P 宏
                macro = "TEST_P"
                test_case = analyze_test_p_macro(
                    cursor=cursor,
                    class_cursor_list=class_cursor_list,
                    target_function_call=target_function_call,
                    unit_test_dir=unit_test_dir,
                    ignore_type_path=ignore_type_path,
                    testBody_definition_info=testBody_definition_info,
                    include_directives=include_directives,
                    macro=macro
                )
                test_case_info_file.append(test_case)

    # 如果是 namespace 或 class，则递归遍历其子节点
    if cursor.kind in [cindex.CursorKind.NAMESPACE, cindex.CursorKind.CLASS_DECL, cindex.CursorKind.CLASS_TEMPLATE]:
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
                target_lib_dir=target_lib_dir
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


    #先查类
    for cmd in tqdm(compile_cmd, desc="Parsing unit test code", unit="cmd"):
        call_graph_all = {}
        root_cursor, src_file = parse_source_file_and_get_cursor(cmd)  # 获取某个单元测试的 AST 的根游标
        method_definitions = []  # 存储当前文件的方法定义详情
        test_case_info_file = []  # 存储每个文件内测试用例信息
        include_directives = set()

        #此处判断是否为单元测试，如果不在单元测试指定dir中，就continue
        if not is_path_contained_in(unit_test_dir, src_file):
            continue

        # 初始化辅助列表
        class_cursor_list = []

        # 遍历根游标的直接子节点
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
                target_lib_dir=target_lib_dir
            )


        file_method_definitions = {src_file: method_definitions}
        test_case_info_all = {src_file: test_case_info_file}

        write_dict_to_json_in_dir(call_graph_all, unit_test_dir, 'call_graph_all.json')
        write_dict_to_json_in_dir(file_method_definitions, unit_test_dir, 'method_definitions.json')
        write_dict_to_json_in_dir(test_case_info_all, unit_test_dir, 'testCase_info.json')




# 主程序入口
if __name__ == '__main__':

    target_lib_dir = '/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom'

    compile_cmd_dir = '/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/build'
    unit_test_dir = '/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test'
    target_function_call = load_public_api('/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom_build').get('libaom.a')

    #指定忽略类型提取路径
    ignore_type_path = ['/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/third_party','/usr/']

    #指定忽略头文件提取路径
    ignore_header_path = ['/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/third_party','/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test']

    # 打印提取的每个单元测试文件中的 API 调用
    main(compile_cmd_dir,target_function_call,unit_test_dir,ignore_type_path,ignore_header_path,target_lib_dir)
