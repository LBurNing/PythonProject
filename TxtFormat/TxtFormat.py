import sys
import os

debug = sys.gettrace()
if debug:
    print("Debug模式\n")
    pathRoot = r'C:\Users\lihehui\Desktop\武将-一体01\衣服外观_武器外观'
    outRoot = r'C:\Users\lihehui\Desktop\武将-一体01\衣服外观_武器外观'
else:
    pathRoot = sys.argv[1]
    outRoot = sys.argv[2]
    print("Release模式\nreadPath: ", pathRoot, " outPath: ", outRoot)

filePaths = []
for root, dirs, files in os.walk(pathRoot):
    for fileName in files:
        if fileName.endswith('.txt'):
            filePaths.append(os.path.join(root, fileName))

def textFormat(path):
    with open(path, 'r') as file:
        context = file.read()

    context = context.replace("－", "-")
    with open(path, 'w') as file:
        file.write(context)

for filePath in filePaths:
    textFormat(filePath)