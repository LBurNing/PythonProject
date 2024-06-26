import oss2
import json
import sys
debug = sys.gettrace()

if debug:
    cdn = 'https://oss-cn-beijing.aliyuncs.com'
    bucket_name = 'lhhburning'
    upLoadFilePath = r"D:\UnityProject\AssetsFramework\product\client\res\updated.json"
else:
    upLoadFilePath = sys.argv[1]
    cdn = sys.argv[2]
    bucket_name = sys.argv[3]
    print("Release模式\nupLoadFilePath: ", upLoadFilePath, " cdn: ", cdn, " bucket_name: ", bucket_name)

accessKeyId = ''
accessKeySecret = ''
auth = oss2.Auth(accessKeyId, accessKeySecret)
bucket = oss2.Bucket(auth, cdn, bucket_name)

def does_bucket_exist(bucket):
    try:
        bucket.get_bucket_info()
    except oss2.exceptions.NoSuchBucket:
        return False
    except:
        raise
    return True

def load_up_load_file(path):
    with open(path, "r", encoding="utf-8") as file:
        text = file.read()
        return json.loads(text)
    
    return

def up_load():
    exist = does_bucket_exist(bucket)
    if not exist:
        print('bucket not exist')
        return
    
    data = load_up_load_file(upLoadFilePath)
    length = len(data)
    progress = 1
    for file in data:
        remote = file['remote']
        local = file['local']
        remote = remote.replace("\\", '/')
        bucket.put_object_from_file(remote, local)

        print("{}/{} {}".format(progress, length, remote))
        progress = progress + 1

up_load()
input("按任意键继续...")