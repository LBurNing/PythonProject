from http.server import SimpleHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import os
import threading
import cgi

# 指定下载和上传文件夹路径
DOWNLOAD_DIR = 'downloads'
UPLOAD_DIR = 'uploads'

class MyHTTPRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        # 处理文件下载
        if self.path == '/download':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            with open(os.path.join(DOWNLOAD_DIR, 'index.html'), 'rb') as f:
                self.wfile.write(f.read())
        else:
            super().do_GET()

    def do_POST(self):
        # 处理文件上传
        if self.path == '/upload':
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD': 'POST'})
            if 'file' in form:
                file_item = form['file']
                filename = os.path.basename(file_item.filename)
                filepath = os.path.join(UPLOAD_DIR, filename)
                
                # 将上传的文件保存到指定的上传文件夹中
                with open(filepath, 'wb') as f:
                    f.write(file_item.file.read())
                
                self.send_response(200)
                self.end_headers()
                print(f'File "{filename}" uploaded successfully'.encode())
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'No file uploaded')
        else:
            super().do_POST()



class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    pass

# 启动 HTTP 服务器
def run(server_class=ThreadedHTTPServer, handler_class=MyHTTPRequestHandler, port=8001):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f'Starting http server on port {port}...')
    httpd.serve_forever()

if __name__ == '__main__':
    # 确保下载和上传文件夹存在，如果不存在则创建它们
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    run()