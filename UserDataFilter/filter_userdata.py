import json
import sys
from datetime import datetime
from pathlib import Path

# 获取当前脚本所在目录
current_dir = Path(__file__).parent

# 输入输出文件路径
input_file = current_dir / "UserData.json"
output_file = current_dir / "UserData_output.json"

# 检查命令行参数
if len(sys.argv) < 2:
    print("请传入时间戳参数，例如：python filter_userdata.py 1773367200")
    sys.exit(1)

filter_timestamp = int(sys.argv[1])

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

print(f"洗数据完成！总 adCount: {total_ad_count}, 条目数: {len(result)}")