import subprocess
import json
import os

def append_functions_to_json(librarypath, output_file):
    # 获取库文件名（去掉路径部分）
    library_name = os.path.basename(librarypath)

    # 使用 subprocess 执行 nm 命令，获取库文件中的所有符号
    result = subprocess.run(
        ['nm', '--demangle', '--defined-only', '-g', librarypath],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        print(f"Error running nm: {result.stderr}")
        return

    # 提取所有 T 类型的符号（函数）
    functions = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] == 'T':  # 确保该行有足够的列，并且符号类型是 'T'
            functions.append(parts[-1])  # 获取符号名

    # 读取现有的 JSON 文件，如果存在的话
    if os.path.exists(output_file):
        with open(output_file, 'r') as f:
            data = json.load(f)
    else:
        data = {}

    # 将函数添加到对应库的条目中
    data[library_name] = functions

    # 将结果写回文件
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)

# 主程序
if __name__ == "__main__":
    # 定义传入的库路径和输出文件路径
    librarypath = "/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/build/libaom_gtest.a"  # 替换成你的库文件路径
    output_file = "/media/fengxiao/3d47419b-aaf4-418e-8ddd-4f2c62bebd8b/workSpace/llmForFuzzDriver/DriverGnerationFromUT/targetLib/aom/build/libaom_gtest.json"  # 替换成你希望保存的 JSON 文件路径

    # 调用函数
    append_functions_to_json(librarypath, output_file)
