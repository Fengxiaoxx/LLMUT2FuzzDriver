from clang import cindex


def parse_source_file_and_get_cursor(src_file: str) -> cindex.Cursor:

    # 检查文件是否存在
    if not os.path.exists(src_file):
        raise FileNotFoundError(f"Source file {src_file} does not exist.")

    header_extension = os.path.splitext(src_file)[1]
    if header_extension == '.h':
        compile_args = ['-x', 'c', '-std=c99']
    else:
        compile_args = ['-x', 'c++', '-std=c++11']

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
    return tu.cursor


import os
import json


def save_api_list_to_json(api_list: list, output_file: str) -> None:
    with open(output_file, 'w', encoding='utf-8') as file:
        json.dump(api_list, file, indent=4)


def main(targetlib_dir: str,output_file:str) -> None:
    api_list = set()
    function_kind = [cindex.CursorKind.FUNCTION_DECL, cindex.CursorKind.CXX_METHOD, cindex.CursorKind.FUNCTION_TEMPLATE]
    for root, dirs, files in os.walk(targetlib_dir):
        # 检查当前的root是否在ignore_dir_list或其子路径中
        for file in files:
            #print(f'*********************{file}*******************************')
            if file.endswith((".h", ".hpp")):
                file_path = os.path.join(root, file)
                cursor = parse_source_file_and_get_cursor(file_path)
                for child in cursor.walk_preorder():
                    if child.kind in function_kind and os.path.basename(child.location.file.name) == file:
                        api_list.add(child.spelling)
    save_api_list_to_json(list(api_list), output_file)


output_file = "/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/build/api_list.json"
target_lib_dir = '/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/xxxx'
ignore_dir_list = ['/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/test','/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/third_party','/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/tools']
main(target_lib_dir,output_file)