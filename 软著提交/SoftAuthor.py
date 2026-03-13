import requests
import json
import time
import random
 
 
def post_request(url, data, authorization_key=None, authorization_token=None, user_agent=None, timeout=30, retry_count=0):
    """
    发送POST请求
    
    参数:
    url: 请求的URL地址
    data: 要发送的数据（字典格式，会自动转换为JSON）
    authorization_key: 授权key（可选）
    authorization_token: 授权token（可选）
    user_agent: User-Agent字符串（可选，默认使用Chrome浏览器UA）
    timeout: 请求超时时间（秒），默认30秒
    retry_count: 重试次数（内部参数，用户无需设置）
    
    返回:
    response: requests.Response 对象
    
    注意:
    如果返回的JSON中errExceptionCode=566113，会自动等待5-10秒后重试，否则正常返回
    """
    # 设置请求头
    headers = {
        'Content-Type': 'application/json; charset=UTF-8'
    }
    
    # 设置User-Agent
    if user_agent is None:
        user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
    headers['User-Agent'] = user_agent
    
    # 如果提供了授权信息，添加到请求头
    # if authorization_key and authorization_token:
    #     headers[authorization_key] = authorization_token
    headers["authorization_key"] = authorization_key
    headers["authorization_token"] = authorization_token
    
    try:
        # 将数据转换为JSON字符串
        json_data = json.dumps(data, ensure_ascii=False)
        
        # 发送POST请求
        response = requests.post(
            url=url,
            data=json_data.encode('utf-8'),
            headers=headers,
            timeout=timeout
        )
        
        # 解析返回结果的JSON
        try:
            result = response.json()
            err_exception_code = result.get('errExceptionCode')
            
            # 如果errExceptionCode=566113，等待5-10秒后再次提交
            if err_exception_code == "566113":
                wait_time = random.uniform(5, 10)
                retry_number = retry_count + 1
                print(f"检测到 errExceptionCode=566113，等待 {wait_time:.2f} 秒后重试... (第 {retry_number} 次重试)")
                time.sleep(wait_time)
                # 递归重试
                return post_request(url, data, authorization_key, authorization_token, user_agent, timeout, retry_count + 1)
            else:
                # 其他情况正常返回
                return response
        except (json.JSONDecodeError, KeyError, AttributeError):
            # 如果无法解析JSON或没有errExceptionCode字段，直接返回响应
            return response
        
    except requests.exceptions.Timeout:
        print(f"请求超时: {url}")
        raise
    except requests.exceptions.ConnectionError:
        print(f"连接错误: {url}")
        raise
    except requests.exceptions.RequestException as e:
        print(f"请求异常: {e}")
        raise
    except Exception as e:
        print(f"未知错误: {e}")
        raise


 
# 使用示例
if __name__ == "__main__":
    
    # 示例2: 带授权的POST请求
    print("=" * 60)
    print("示例2: 带授权的POST请求")
    print("=" * 60)
    
    url2 = "https://gateway.ccopyright.com.cn/registerQuerySoftServer/userCenter/submitSealMaterial/案件号码"
    # data2 = {
    #     "action": "create",
    #     "title": "测试文章",
    #     "content": "这是一篇测试文章的内容"
    # }
    data2 = {
    }
    auth_key = "C106nNZedqHeOvcNa7Dcg48lNYDwcJ8R"
    auth_token = "eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFMyNTYifQ.eyJhY2NvdW50SWQiOiIxMDQxMDIyMjEyNDAxOTY3MTA0IiwibG9naW5UeXBlIjowLCJpc3MiOiJDMTA2bk5aZWRxSGVPdmNOYTdEY2c0OGxOWUR3Y0o4UiJ9.NgRS0rTjO6JnqtVCMDShYd-Od_jZM2gdvHpREOwAFFc"
    
    try:
        response2 = post_request(
            url=url2,
            data=data2,
            authorization_key=auth_key,
            authorization_token=auth_token,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
        )
        print(f"状态码: {response2.status_code}")
        print(f"响应内容: {response2.text[:200]}...")
        
        # 解析返回的JSON结果
        try:
            result = response2.json()
            print(f"解析后的JSON: {json.dumps(result, ensure_ascii=False, indent=2)}")
            if 'errExceptionCode' in result:
                print(f"errExceptionCode: {result['errExceptionCode']}")
        except json.JSONDecodeError:
            print("响应不是有效的JSON格式")
    except Exception as e:
        print(f"请求失败: {e}")
    
    print("\n")
    
    # 示例3: 使用自定义授权头
    print("=" * 60)
    print("示例3: 使用自定义授权头")
    print("=" * 60)
