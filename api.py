from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import subprocess
import os
import logging
import sys
import locale
from werkzeug.utils import secure_filename
import re

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # 启用CORS支持

@app.route('/', methods=['GET'])
def home():
    return '''
    <html>
        <head>
            <title>KET-RAG API</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                pre { background-color: #f4f4f4; padding: 15px; border-radius: 5px; }
            </style>
        </head>
        <body>
            <h1>KET-RAG API 服务</h1>
            <p>这是一个用于查询的 API 服务。请使用 POST 请求访问 /query 端点。</p>
            <h2>使用示例：</h2>
            <pre>
curl -X POST http://localhost:5000/query \\
     -H "Content-Type: application/json" \\
     -d '{"query":"QS三厂有几个机组", "root":"./ptoduct", "method":"global"}'
            </pre>
            <p>或者使用前端应用访问此 API。</p>
        </body>
    </html>
    '''

@app.route('/query', methods=['POST'])
def query():
    try:
        logger.info("Received query request")
        data = request.get_json()
        if data is None:
            logger.error("No JSON data provided")
            return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
            
        query_text = data.get('query', '')
        root_dir = data.get('root', './ptoduct')
        method = data.get('method', 'local')
        community_level = data.get('community_level', None)
        response_type = data.get('response_type', None)

        logger.info(f"Processing query: {query_text}")
        logger.info(f"Using root directory: {root_dir}")
        logger.info(f"Using method: {method}")
        if community_level is not None:
            logger.info(f"Using community level: {community_level}")

        # 确保在正确的目录下执行命令
        current_dir = os.getcwd()
        api_dir = os.path.dirname(os.path.abspath(__file__))
        logger.info(f"Current directory: {current_dir}")
        logger.info(f"API directory: {api_dir}")
        
        os.chdir(api_dir)

        # 构建命令
        command = f"graphrag query --root {root_dir} --method {method}"
        if community_level is not None:
            command += f" --community-level {community_level}"
        if response_type is not None:
            command += f" --response-type \"{response_type}\""
        command += f" --query \"{query_text}\""
        logger.info(f"Executing command: {command}")

        # 使用subprocess.Popen来执行命令，使用系统默认编码
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding=locale.getpreferredencoding(False)  # 使用系统默认编码
        )

        # 获取输出
        stdout, stderr = process.communicate()
        
        # 恢复原来的工作目录
        os.chdir(current_dir)

        logger.info("Command executed successfully")
        logger.info(f"Command output: {stdout}")
        if stderr:
            logger.warning(f"Command stderr: {stderr}")

        # 检查命令是否成功执行
        if process.returncode != 0:
            return jsonify({
                'success': False,
                'error': f"Command failed with return code {process.returncode}. Error: {stderr}"
            }), 500

        # 检查是否有实际输出
        if not stdout or not stdout.strip():
            return jsonify({
                'success': False,
                'error': "Command executed but returned no output. Please check if the query is valid."
            }), 400

        # 过滤掉 TensorFlow 警告信息
        filtered_stderr = '\n'.join([line for line in stderr.split('\n') 
                                   if not line.startswith('WARNING:tensorflow:') 
                                   and not 'oneDNN custom operations' in line])

        return jsonify({
            'success': True,
            'result': stdout.strip(),
            'error': filtered_stderr if filtered_stderr else None
        })
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '未检测到文件'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': '未选择文件'}), 400
        # 保存路径
        upload_folder = r'D:/laboratory/KET-RAG/ptoduct/input'
        os.makedirs(upload_folder, exist_ok=True)
        filename = secure_filename(file.filename)
        save_path = os.path.join(upload_folder, filename)
        file.save(save_path)
        return jsonify({'success': True, 'filename': filename, 'message': '文件上传成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/process-uploaded-files', methods=['POST'])
def process_uploaded_files():
    try:
        # 切换到脚本目录
        current_dir = os.getcwd()
        api_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(api_dir)
        command = "python -m graphrag index --root ptoduct/"
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding=locale.getpreferredencoding(False)
        )
        # 等待更长时间，防止超时
        try:
            stdout, stderr = process.communicate(timeout=3600)  # 最长等1小时
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            os.chdir(current_dir)
            return jsonify({'success': False, 'error': '处理超时', 'stdout': stdout, 'stderr': stderr}), 500
        os.chdir(current_dir)
        if process.returncode != 0:
            return jsonify({'success': False, 'error': stderr, 'stdout': stdout}), 500
        return jsonify({'success': True, 'result': stdout, 'stderr': stderr})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/process-uploaded-files-stream', methods=['GET'])
def process_uploaded_files_stream():
    def remove_emoji(text):
        return re.sub(r'[^\u0000-\uFFFF]', '', text)
    def generate():
        current_dir = os.getcwd()
        api_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(api_dir)
        command = "python -m graphrag index --root ptoduct/"
        import os as _os
        env = _os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding='utf-8',
            bufsize=1,
            env=env
        )
        try:
            for line in iter(process.stdout.readline, ''):
                yield f"data: {remove_emoji(line.rstrip())}\n\n"
            process.stdout.close()
            process.wait()
        finally:
            os.chdir(current_dir)
    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    try:
        logger.info("Starting Flask server...")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Current working directory: {os.getcwd()}")
        logger.info(f"System encoding: {locale.getpreferredencoding(False)}")
        app.run(host='127.0.0.1', port=5000, debug=False)
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}", exc_info=True) 