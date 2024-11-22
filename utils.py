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
