from flask import Flask, request, Response
import requests

app = Flask(__name__)

# 代理路径，例如 /proxy/xxx 会转发到远程服务器
REMOTE_BASE = "https://bygb-cdn2.cq798.cn"

@app.route('/proxy/<path:path>')
def proxy(path):
    # 构造完整远程 URL
    url = f"{REMOTE_BASE}/{path}"
    
    # 转发请求到远程服务器
    resp = requests.get(url)
    
    # 构造响应，并添加允许跨域的头
    excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
    headers = [(name, value) for (name, value) in resp.raw.headers.items() if name.lower() not in excluded_headers]

    # 添加允许跨域
    headers.append(('Access-Control-Allow-Origin', '*'))

    return Response(resp.content, resp.status_code, headers)

if __name__ == "__main__":
    app.run(port=8081, debug=True)
