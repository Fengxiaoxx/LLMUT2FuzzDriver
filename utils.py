import json
import os
from clang.cindex import CompilationDatabase


# 加载 compile_commands.json
def load_compile_commands(path):
    comp_db = CompilationDatabase.fromDirectory(path)
    all_compile_commands = comp_db.getAllCompileCommands()
    return all_compile_commands


# 加载公共 API
def load_public_api(path):
    # 自动添加文件名 public_api.json
    compile_commands_path = os.path.join(path, 'public_api.json')
    with open(compile_commands_path, 'r') as file:
        return json.load(file)


def is_path_contained_in(base_path, check_path):
    """
    判断 check_path 是否位于 base_path 或其子目录中。

    :param base_path: 基准路径（目录）
    :param check_path: 要检查的路径（文件或目录）
    :return: True 如果 check_path 位于 base_path 或其子目录中，否则 False
    """
    # 转换为绝对路径，确保路径判断的可靠性
    abs_base_path = os.path.abspath(base_path)
    abs_check_path = os.path.abspath(check_path)

    # 确保 base_path 是一个目录
    if not os.path.isdir(abs_base_path):
        raise ValueError(f"The base_path '{base_path}' is not a valid directory.")

    # 检查 check_path 是否以 base_path 为前缀，表明在目录内
    return abs_check_path.startswith(abs_base_path + os.sep)


def is_path_contained_in_any(base_paths, check_path):
    """
    判断 check_path 是否位于 base_paths 列表中任意一个路径或其子目录中。

    :param base_paths: 基准路径列表（每个元素是一个目录路径）
    :param check_path: 要检查的路径（文件或目录）
    :return: True 如果 check_path 位于 base_paths 中的任意路径或其子目录中，否则 False
    """
    # 转换为绝对路径，确保路径判断的可靠性
    abs_check_path = os.path.abspath(check_path)

    # 检查每个 base_path 是否有效
    for base_path in base_paths:
        # 转换为绝对路径
        abs_base_path = os.path.abspath(base_path)

        # 确保 base_path 是一个目录
        if not os.path.isdir(abs_base_path):
            raise ValueError(f"The base_path '{base_path}' is not a valid directory.")

        # 如果 check_path 以 base_path 为前缀，表示位于该目录内
        if abs_check_path.startswith(abs_base_path + os.sep):
            return True

    # 如果遍历所有 base_paths 后没有找到符合条件的路径，返回 False
    return False


def process_compile_args(cmd):
    """
    处理编译参数列表，移除与解析无关的选项，并将优化级别设置为 -O0。

    参数：
        cmd (clang.cindex.CompileCommand): 包含编译参数的编译命令。

    返回：
        list: 处理后的编译参数列表。
    """
    # 移除第一个参数（通常是编译器名称）
    compile_args = list(cmd.arguments)[1:]

    # 移除 '-c' 参数
    compile_args = [arg for i, arg in enumerate(compile_args)
                    if arg != '-c' and (i == 0 or compile_args[i - 1] != '-c')]

    # 移除 '-o' 及其后续参数
    cleaned_args = []
    skip_next = False
    for arg in compile_args:
        if skip_next:
            skip_next = False
            continue
        if arg == '-o':
            skip_next = True  # 跳过 '-o' 的下一个参数
        else:
            cleaned_args.append(arg)

    # 查找并移除现有的优化参数（如 '-O1', '-O2', '-O3', '-Os', '-Ofast'）
    optimization_flags = ['-O0', '-O1', '-O2', '-O3', '-Os', '-Ofast']
    cleaned_args = [arg for arg in cleaned_args if arg not in optimization_flags]

    # 添加 '-O0' 参数以禁用优化
    cleaned_args.append('-O0')

    return cleaned_args


import json


def write_dict_to_json_in_dir(data_dict: dict, target_dir: str, file_name:str):
    """
    将字典内容追加到指定目录的 JSON 文件，文件名为硬编码的 method_definitions.json。
    如果文件不存在，则创建文件并写入。
    """

    # 确保目标目录存在
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    # 组合目标文件路径
    file_path = os.path.join(target_dir, file_name)

    # 如果文件存在，先读取旧内容并合并
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as json_file:
            try:
                existing_data = json.load(json_file)
            except json.JSONDecodeError:
                existing_data = {}
        # 合并字典（旧内容和新内容）
        if isinstance(existing_data, dict):
            data_dict = {**existing_data, **data_dict}
        else:
            raise ValueError("Existing data is not a dictionary!")

    # 写入合并后的数据
    with open(file_path, 'w', encoding='utf-8') as json_file:
        json.dump(data_dict, json_file, indent=4, ensure_ascii=False)


