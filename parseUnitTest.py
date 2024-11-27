from utils import load_compile_commands, load_public_api, process_compile_args, is_path_contained_in, write_dict_to_json_in_dir, is_path_contained_in_any
from clang import cindex  # 导入 Clang 的 Python 接口模块
from typing import List, Tuple, Optional, Dict, Any
import os

# 设置 Clang 库的路径
cindex.Config.set_library_file('/usr/lib/llvm-15/lib/libclang.so.1')


def get_type_ref_definition(cursor_reference: cindex.Cursor) -> Dict:

    cursor_ref_def_file = cursor_reference.location.file.name
    cursor_ref_def_start_line = cursor_reference.extent.start.line
    cursor_ref_def_end_line = cursor_reference.extent.end.line

    if cursor_reference.kind == cindex.CursorKind.TYPEDEF_DECL:
        # 获取 typedef 声明对应的类型声明
        typedef_type = cursor_reference.underlying_typedef_type
        typedef_decl = typedef_type.get_declaration()

        #借助extent来区分
        if not typedef_decl.extent == cursor_reference.extent and typedef_decl.location.file is not None:

            cursor_underlying_file = typedef_decl.location.file.name
            cursor_underlying_start_line = typedef_decl.extent.start.line
            cursor_underlying_end_line = typedef_decl.extent.end.line
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
            'type_def': {
                'file': cursor_ref_def_file,
                'start_line': cursor_ref_def_start_line,
                'end_line': cursor_ref_def_end_line,
            }
        }
    return type_def_info


def get_aux_function_definition(cursor_reference: cindex.Cursor) -> Optional[Dict[str, Any]]:
    if cursor_reference is None:
        return None

    try:
        if cursor_reference.is_definition():
            flag = True
        else:
            flag = False

        if cursor_reference.location.file and cursor_reference.extent:
            aux_function_info = {
                'file': cursor_reference.location.file.name,
                'start_line': cursor_reference.extent.start.line,
                'end_line': cursor_reference.extent.end.line,
                'isSrcCode': flag
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

def collect_function_call_details(testBody: cindex.Cursor, target_function_call: List, unit_test_dir: str, ignore_type_path:List) -> Tuple[List[str], List[cindex.Cursor], List[cindex.Cursor]]:
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
                if is_valid_type_ref(referenced) and not  is_path_contained_in_any(ignore_type_path,ref_loc) and not ref_spelling.endswith("_Test"):
                    type_ref_list.add(referenced)

    except Exception as e:
        print(f"Error occurred: {e}")
        return [], [], []

    return target_function_call_in_testbody, aux_function_cursors, list(type_ref_list)



def get_final_gtest_base_class(
    class_cursor: cindex.Cursor,
    root_cursor: cindex.Cursor,
    checked_classes=None,
    class_cursor_list = []
) -> Tuple[str, List[cindex.Cursor]]:

    base_class_list = []
    result_final = 'None'

    class_cursor_list.append(class_cursor)  # 保存当前类的 cursor

    if checked_classes is None:
        checked_classes = set()

    # 确保输入是类声明
    if class_cursor.kind not in [cindex.CursorKind.CLASS_DECL, cindex.CursorKind.CLASS_TEMPLATE]:
        return 'None', class_cursor_list

    # 防止循环继承导致的无限递归
    class_usr = class_cursor.get_usr()
    if class_usr in checked_classes:
        return 'None', class_cursor_list
    checked_classes.add(class_usr)

    # 查找当前类的所有基类
    for cursor in root_cursor.walk_preorder():
        if cursor.spelling == class_cursor.spelling and cursor.kind in [cindex.CursorKind.CLASS_DECL, cindex.CursorKind.CLASS_TEMPLATE]:
            base_class_list.append(cursor)

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
                    # 递归检查基类
                    result, child_visited = get_final_gtest_base_class(
                        base_decl, root_cursor, checked_classes,class_cursor_list
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


def main(compile_cmd_dir:str,target_function_call:list,unit_test_dir:str,ignore_type_path:List):
    compile_cmd = load_compile_commands(compile_cmd_dir)
    file_method_definitions = {}  # 新增字典，用于存储每个文件的方法定义详情
    test_case_info_all = {}

    for cmd in compile_cmd:

        root_cursor,src_file = parse_source_file_and_get_cursor(cmd)  # 获取某个单元测试的 AST 的根游标
        method_definitions = []  # 存储当前文件的自定义详情
        testCase_num = 0 #对测试用例编号
        test_case_info_file = {} #存储每个文件内测试用例信息
        include_directives = []

        for cursor in root_cursor.walk_preorder():

            if cursor.kind == cindex.CursorKind.INCLUSION_DIRECTIVE and cursor.location.file.name == src_file:
                include_directives.append(cursor.spelling)

            if (
                    cursor.kind in (cindex.CursorKind.FUNCTION_DECL, cindex.CursorKind.CXX_METHOD, cindex.CursorKind.FUNCTION_TEMPLATE) and
                    cursor.is_definition() and
                    cursor.location.file.name == src_file and
                    cursor.spelling != "TestBody"
            ):

                method_definition_detail = pack_function_definitions(cursor)
                method_definitions.append(method_definition_detail)

            parent_class = cursor.semantic_parent

            if cursor.spelling == "TestBody" and parent_class.kind == cindex.CursorKind.CLASS_DECL and cursor.is_definition():

                print("=======================分割线===================================")
                testCase_num += 1
                #取本方法定义位置
                testBody_file = cursor.location.file.name
                testBody_start_line = cursor.extent.start.line
                testBody_end_line = cursor.extent.end.line

                testBody_definition_info = {
                    "file": testBody_file,
                    "start_line": testBody_start_line,
                    "end_line": testBody_end_line
                }

                final_base_class,class_cursor_list = get_final_gtest_base_class(parent_class,root_cursor) #final_base_class表示最终的基类，class_cursor_list表示所有被访问到的基类

                if is_derived_from_testing_test(parent_class): #通过TestBody所属类是否直接继承自::testing::TEST类来判断宏的类型
                    aux_function_definition_list = []
                    type_definition_list = []

                    target_function_calls, aux_function_cursor_list ,type_ref_list = collect_function_call_details(cursor,target_function_call,unit_test_dir,ignore_type_path) # 获取待测目标函数调用和自定义辅助函数

                    for aux_function_cursor in aux_function_cursor_list:
                        aux_function_definition_list.append(get_aux_function_definition(aux_function_cursor))

                    for type_ref in type_ref_list:
                        type_definition_list.append(get_type_ref_definition(type_ref))

                     # 生成键名并存储数据
                    test_case_key = f'testCase_{testCase_num}'  # 动态生成键
                    test_case_info_file[test_case_key] = {
                        "macro":"TEST",
                        "include_directives":include_directives,
                        "testBody_definition_info": testBody_definition_info,
                        "aux_function_definition_list": aux_function_definition_list,
                        "type_definition_list": type_definition_list,
                        "target_function_called": target_function_calls
                    }



                else:
                    if final_base_class == "Test": #说明是TEST_F宏
                        print("这是TEST_F")
                    elif final_base_class == "TestWithParam": #说明是TEST_P宏
                        print("这是TEST_P")
                    else:
                        print("无")

        file_method_definitions[src_file] = method_definitions
        test_case_info_all[src_file] = test_case_info_file

        write_dict_to_json_in_dir(file_method_definitions, unit_test_dir, 'method_definitions.json')
        write_dict_to_json_in_dir(test_case_info_all,unit_test_dir,'testCase_info.json')

# 主程序入口
if __name__ == '__main__':
    compile_cmd_dir = '/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/build'
    unit_test_dir = '/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test'
    target_function_call = load_public_api('/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom_build').get('libaom.a')

    #指定忽略类型提取路径
    ignore_type_path = ['/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/third_party']
    # 打印提取的每个单元测试文件中的 API 调用
    main(compile_cmd_dir,target_function_call,unit_test_dir,ignore_type_path)
