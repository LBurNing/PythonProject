import xml.etree.ElementTree as ET
import os
import json

def checkXls_xml(xmlPath, excelPath):
    debug = ""
    excel_dic = {}
    
    # 打开XML文件
    tree = ET.parse(xmlPath)
    # 获取根元素
    root = tree.getroot()
    # 遍历子元素
    for item in root.findall('.//add'):
        name = item.get('key')
        value = item.get('value')
        excel_dic[name] = value

    excelPaths = os.walk(excelPath)
    for root, dirs, files in excelPaths:
        for file in files:
            if file not in excel_dic:
                debug = debug + file + "\n"
    
    return debug

def checkXls_json(jsonPath, excelPath):
    debug = ""
    data = ""
    with open(jsonPath, 'r', encoding="utf-8") as file:
        data = json.load(file)
    
    # 提取 filename 字段
    filename_dict = {item['filename']: True for item in data}
    excelPaths = os.walk(excelPath)
    for root, dirs, files in excelPaths:
        for file in files:
            if file not in filename_dict:
                debug = debug + file + "\n"
    return debug

excelPath = "D:\\FGCQ3\\config\\"
client_debug = checkXls_xml('D:\\FGCQ3\\tools\\ExcelExport\\client\\setting.config', excelPath)
server_debug = checkXls_json('D:\\FGCQ3\\tools\\ExcelExport\\server\\config.json', excelPath)

with open("client.txt", "w") as file:
    file.write(client_debug)

with open("server.txt", "w") as file:
    file.write(server_debug)

def merge(path1, path2):
    dic1 = set()
    dic2 = set()

    with open(path1, 'r') as file:
        for line in file:
            dic1.add(line.strip())

    with open(path2, 'r') as file:
        for line in file:
            dic2.add(line.strip())

    # 保留两个文件中都存在的行
    common_lines = dic1.intersection(dic2)
    return common_lines

result = merge("client.txt", "server.txt")
