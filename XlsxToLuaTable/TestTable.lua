--The generated code cannot be modified!!
TestTable = {} 
local __value__ = {
    [10086] = {10086, "超赛1", true, 20, 160, 23.33, {101,102,103,104}, {true,false,false,false}, {"描述1","描述2","描述3","描述4"}, {10.2,10.3,10.4,10.5}},
    [10087] = {10087, "超赛2", true, 21, 161, 24.33, {101,102,103,104}, {true,false,true,true}, {"描述1","描述2","描述3","描述5"}, {10.2,10.3,10.4,10.6}},
    [10088] = {10088, "超赛3", true, 22, 162, 25.33, {101,102,103,104}, {true,false,true,false}, {"描述1","描述2","描述3","描述6"}, {10.2,10.3,10.4,10.7}},
    [10089] = {10089, "超赛4", true, 23, 163, 26.33, {101,102,103,104}, {true,false,true,true}, {"描述1","描述2","描述3","描述7"}, {10.2,10.3,10.4,10.8}},
    [10090] = {10090, "超赛5", true, 24, 164, 27.33, {101,102,103,104}, {true,false,false,false}, {"描述1","描述2","描述3","描述8"}, {10.2,10.3,10.4,10.9}},
}

local __key__ = {
   ID = 1,
   Name = 2,
   Sex = 3,
   Age = 4,
   Height = 5,
   Width = 6,
   skillIds = 7,
   skillOpens = 8,
   skillDesc = 9,
   cds = 10,
   
}

local __index__ = {10086,10087,10088,10089,10090}
TestTable.len = 5

local function GetValue(tTable, vKey)
	local nIndex = __key__[vKey]
	if not nIndex then
		return nil
	end

	return tTable[nIndex]
end

local function Get(tTable, vKey)
	if vKey == "tMap" then
		return __value__
	end

	if vKey == "tList" then
		return __index__
	end

	return __value__[vKey]
end

local function ReadOnly(tTable, vKey, vValue)
	print("TestTable A read-only table cannot be modified, key: "..vKey.." be changed to: "..vValue)
end

for nId, tCfg in pairs(__value__) do
	setmetatable(tCfg, {__index = GetValue, __newindex = ReadOnly})
end

setmetatable(TestTable, {__index = Get, __newindex = ReadOnly})