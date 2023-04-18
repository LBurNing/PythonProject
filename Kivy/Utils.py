import os

def get_files_by_suffix(path, suffix):
    """
    获取指定路径下所有指定后缀名的文件路径
    :param path: 路径
    :param suffix: 后缀名，例如'.txt'
    :return: 文件路径列表
    """
    file_list = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(suffix):
                file_path = os.path.join(root, file)
                file_list.append(file_path)
    return file_list