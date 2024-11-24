from utils import load_compile_commands, load_public_api, process_compile_args, is_path_contained_in
from clang import cindex  # 导入 Clang 的 Python 接口模块
from typing import List, Tuple

# 设置 Clang 库的路径
cindex.Config.set_library_file('/usr/lib/llvm-15/lib/libclang.so.1')


def collect_function_call_details(testBody:cindex.Cursor,target_function_call:List, unit_test_dir:str) -> Tuple[List[str], List[cindex.Cursor]]:
    target_function_set = set() # 使用集合来跟踪已添加的元素，确保唯一性
    aux_function_cursors = []  #用来存放那些由开发者定义在单元测试项目中的辅助函数的cursor
    target_function_call_in_testbody = []

    for cursor in testBody.walk_preorder():
        if cursor.kind == cindex.CursorKind.CALL_EXPR:
            if cursor.spelling in target_function_call and cursor.spelling not in target_function_set:
                target_function_call_in_testbody.append(cursor.spelling)
                target_function_set.add(cursor.spelling)
            else:
                referenced = cursor.referenced
                if (
                        referenced and
                        referenced.location and
                        referenced.location.file and
                        referenced.kind in (cindex.CursorKind.CXX_METHOD, cindex.CursorKind.FUNCTION_DECL)
                ):
                    if is_path_contained_in(unit_test_dir,referenced.location.file.name):
                        aux_function_cursors.append(referenced)
    target_function_call_in_testbody[:] = list(set(target_function_call_in_testbody)) # 确保 target_function_call_in_testbody 列表中没有重复值
    return target_function_call_in_testbody,aux_function_cursors


def get_final_gtest_base_class(class_cursor: cindex.Cursor, root_cursor: cindex.Cursor, checked_classes=None) -> str:
    if checked_classes is None:
        checked_classes = set()

    # 确保输入是类声明
    if class_cursor.kind not in [cindex.CursorKind.CLASS_DECL, cindex.CursorKind.CLASS_TEMPLATE]:
        return 'None'

    # 防止循环继承导致的无限递归
    class_usr = class_cursor.get_usr()
    if class_usr in checked_classes:
        return 'None'
    checked_classes.add(class_usr)

    for cursor in root_cursor.walk_preorder():
        if cursor.spelling == class_cursor.spelling and cursor.kind in [cindex.CursorKind.CLASS_DECL, cindex.CursorKind.CLASS_TEMPLATE]:
            for base in cursor.get_children():
                if base.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
                    base_type = base.type
                    base_decl = base_type.get_declaration()
                    base_usr = base_decl.get_usr()
                    if base_usr == 'c:@N@testing@S@Test':
                        return 'Test'
                    elif base_usr.startswith('c:@N@testing@ST>1#T@TestWithParam'):
                        return 'TestWithParam'
                    else:
                        # 继续递归检查基类
                        result = get_final_gtest_base_class(base_decl, root_cursor, checked_classes)
                        if result != 'None':
                            return result
    return 'None'


def is_derived_from_testing_test(class_cursor:cindex.Cursor) ->bool:
    # 确保输入是类声明
    if class_cursor.kind not in [cindex.CursorKind.CLASS_DECL,cindex.CursorKind.CLASS_TEMPLATE]:
        return False

    # 遍历基类
    for base in class_cursor.get_children():
        if base.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
            base_type = base.type
            base_decl = base_type.get_declaration()
            # 获取基类的完全限定名
            base_name = base_decl.get_usr()
            # 检查是否为 ::testing::Test
            if base_name == 'c:@N@testing@S@Test':
                return True


def parse_source_file_and_get_cursor(cmd: cindex.CompileCommand) -> cindex.Cursor:
    src_file = cmd.filename  # 获取源文件路径
    # 跳过文件路径不存在或单元测试路径不存在的情况
    compile_args = process_compile_args(cmd)
    index = cindex.Index.create()
    # 解析源文件，生成 TranslationUnit
    tu = index.parse(
        src_file,
        args=compile_args,
        options=cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
    )
    return tu.cursor


def main(compile_cmd_dir:str,target_function_call:list,unit_test_dir:str):
    compile_cmd = load_compile_commands(compile_cmd_dir)
    for cmd in compile_cmd:
        root_cursor = parse_source_file_and_get_cursor(cmd)  # 获取某个单元测试的 AST 的根游标
        for cursor in root_cursor.walk_preorder():
            parent_class = cursor.semantic_parent
            if cursor.spelling == "TestBody" and parent_class.kind == cindex.CursorKind.CLASS_DECL and cursor.is_definition():
                final_base_class = get_final_gtest_base_class(parent_class,root_cursor)
                if is_derived_from_testing_test(parent_class): #通过TestBody所属类是否直接继承自::testing::TEST类来判断宏的类型
                    target_function_calls, aux_function_cursors = collect_function_call_details(cursor,target_function_call,unit_test_dir)
                    print(target_function_calls,aux_function_cursors)
                else:
                    if final_base_class == "Test":
                        print("这是TEST_F")
                    elif final_base_class == "TestWithParam":
                        print("这是TEST_P")
                    else:
                        print("无")



# 主程序入口
if __name__ == '__main__':
    compile_cmd_dir = '/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/build'
    unit_test_dir = '/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/test'
    target_function_call = load_public_api('/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom_build').get('libaom.a')
    # 打印提取的每个单元测试文件中的 API 调用
    main(compile_cmd_dir,target_function_call,unit_test_dir)
