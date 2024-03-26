import pandas as pd
import math

INT_TYPE = 'int'
BOOL_TYPE = 'bool'
STRING_TYPE = 'string'
FLOAT_TYPE = 'float'
INT_ARRAY_TYPE = 'int[]'
BOOL_ARRAY_TYPE = 'bool[]'
STRING_ARRAY_TYPE = 'string[]'
FLOAT_ARRAY_TYPE = 'float[]'

VALUE_NAME = '__value__'
INDEX_NAME = '__index__'
KEY_NAME = '__key__'
LEN_NAME = 'len'

def isnan(value):
    try:
        # 尝试将值转换为浮点数
        float_value = float(value)
        return math.isnan(float_value)
    except (TypeError, ValueError):
        # 如果转换失败，说明值不是数字或NaN
        return False

def readXlsx(xlsxPath):
    df = pd.read_excel(xlsxPath, header=None)
    return df

def FrmatIntArray(text):
    return '{' + text + '}'

def FrmatFloatArray(text):
    return '{' + text + '}'

def FrmatStringArray(text):
    outStr = "{"
    for value in text.split(','):
        outStr += f'"{value}",'
    
    outStr = outStr[:len(outStr) - 1]
    outStr += "}"
    return outStr

def FrmatBoolArray(text):
    outStr = "{"
    for value in text.split(','):
        outStr += str(bool(int(value))).lower() + ","
    
    outStr = outStr[:len(outStr) - 1]
    outStr += "}"
    return outStr

def FormatValue(value, type):
    if pd.isna(value):  # 处理空值
        if type == INT_TYPE or type == FLOAT_TYPE:
            value = 0
        elif type == STRING_TYPE:
            value = '""'
        elif type == BOOL_TYPE:
            value = 'false'
        elif type == INT_ARRAY_TYPE or type == STRING_ARRAY_TYPE or type == BOOL_ARRAY_TYPE or type == FLOAT_ARRAY_TYPE:
            value = '{}'
    else:
        value = str(value).strip()  # 去除字符串两端的空格

        # 根据字段类型进行处理
        if type == STRING_TYPE:
            value = f'"{value}"'
        elif type == INT_TYPE:
            value = int(value)
        elif type == FLOAT_TYPE:
            value = float(value)
        elif type == BOOL_TYPE:
            value = str(bool(value)).lower()
        elif type == INT_ARRAY_TYPE:
            value = FrmatIntArray(value)
        elif type == STRING_ARRAY_TYPE:
            value = FrmatStringArray(value)
        elif type == BOOL_ARRAY_TYPE:
            value = FrmatBoolArray(value)
        elif type == FLOAT_ARRAY_TYPE:
            value = FrmatFloatArray(value)
    
    return value

def toTable(xlsxPath, tableName):
    df = readXlsx(xlsxPath)
    # 获取字段名和类型
    field_names = list(df.iloc[1])
    field_types = list(df.iloc[2])
    key2Index = {}
    Index2Id = {}
    length = 0

    table = '--The generated code cannot be modified!!\n'
    table+=(tableName + ' = {} \nlocal ' + f'{VALUE_NAME} = ' + '{\n')
    # 遍历每一行数据，从第四行开始
    for index, row in df.iloc[3:].iterrows():
        # 获取行的 ID（假设 ID 在第一列）
        row_id = row[0]
        table+=(f'    [{row_id}] = {{')
        length+=1
        Index2Id[length] = row_id
        # 遍历每一列数据（不包括第一列）
        for column, value in row.items():
            # 获取字段类型
            field_type = field_types[column]
            field_name = field_names[column]

            if isnan(field_type) or isnan(field_name):
                continue

            value = FormatValue(value, field_type)
            key2Index[field_name] = column + 1
            table+=(f'{value}, ')

        table = table[:len(table) - 2]
        table+=('},\n')

    # 写入 Lua 的 table 结束部分
    table+=('}\n\n')
    table+=('local ' + f'{KEY_NAME} = ' + '{\n')
    for key, value in key2Index.items():
        table+=(f'   {key} = {value},\n')
    table+=('}\n\n')

    table+=('local ' + f'{INDEX_NAME} = ' + '{')
    for key, value in Index2Id.items():
        table+=(f'{value},')
    table = table[:len(table) - 1]
    table+=('}\n')

    table+=(f'{tableName}.{LEN_NAME} = ' + f'{length}' + '\n\n')

    #GetValue
    table+=('local function GetValue(tTable, vKey)\n')
    table+=(f'\tlocal nIndex = {KEY_NAME}[vKey]\n')
    table+=('\tif not nIndex then\n\t\treturn nil\n\tend\n\n\treturn tTable[nIndex]\nend\n\n')

    #Get
    table+=('local function Get(tTable, vKey)\n')
    table+=(f'\tif vKey == "tMap" then\n\t\treturn {VALUE_NAME}\n\tend\n\n')
    table+=(f'\tif vKey == "tList" then\n\t\treturn {INDEX_NAME}\n\tend\n\n')
    table+=(f'\treturn {VALUE_NAME}[vKey]\nend\n\n')

    table+=(f'local function ReadOnly(tTable, vKey, vValue)\n\tprint("{tableName} A read-only table cannot be modified, key: "..vKey.." be changed to: "..vValue)\nend\n\n')
    table+=(f'for nId, tCfg in pairs({VALUE_NAME}) do\n\t' + 'setmetatable(tCfg, {__index = GetValue, __newindex = ReadOnly})\nend\n\n')
    table+=(f'setmetatable({tableName}, ' + '{__index = Get, __newindex = ReadOnly})')

    return table

def writeTable(tablePath, table):
    with open(tablePath, 'w', encoding="utf-8") as f:
        f.write(table)

tableName = 'TestTable'
table = toTable('XlsxToLuaTable\Test.xlsx', tableName)
writeTable('XlsxToLuaTable\\' + tableName + '.lua', table)
