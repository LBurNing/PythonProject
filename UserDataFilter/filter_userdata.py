import json
import sys
from datetime import datetime

if len(sys.argv) < 2:
    print("请传入时间戳参数，例如：python filter_userdata.py 1773367200")
    sys.exit(1)

filter_timestamp = int(sys.argv[1])

input_file = r"C:\Users\lihehui\Desktop\UserDataFilter\UserData.json"
output_file = r"C:\Users\lihehui\Desktop\UserDataFilter\UserData_output.json"

result = []
total_ad_count = 0

with open(input_file, "r", encoding="utf-8") as f:
    for line in f:
        item = json.loads(line)
        user = item.get("userData", {})
        last_login = item.get("lastLoginTime", 0)

        if last_login > filter_timestamp:
            ad_count = user.get("adCount", 0)
            total_ad_count += ad_count

            result.append({
                "id": item.get("id"),
                "adCount": ad_count,
                "lastLoginTime": last_login,
                "lastLoginTimeStr": datetime.fromtimestamp(last_login).strftime("%Y-%m-%d %H:%M:%S")
            })

output_data = {
    "totalAdCount": total_ad_count,
    "users": result
}

with open(output_file, "w", encoding="utf-8") as f:
    json.dump(output_data, f, ensure_ascii=False, indent=2)

print(f"完成！总 adCount: {total_ad_count}, 条目数: {len(result)}")