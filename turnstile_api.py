import os
from flask import Flask, request, jsonify
from BypassTurns import solve_turnstile_token

app = Flask(__name__)


@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'api': 'turnstile-solver',
        'usage': 'POST /solve-turnstile com JSON: '
                 '{"url": "...", "proxy": "http://host:port (opcional)"}'
    })


@app.route('/solve-turnstile', methods=['POST'])
def solve_turnstile():
    data = request.get_json(silent=True) or {}

    url = data.get('url')
    if not url:
        return jsonify({'success': False, 'error': 'Campo obrigatorio: url'}), 400

    if not url.startswith('http'):
        url = 'https://' + url

    proxy = data.get('proxy')

    try:
        attempts = int(data.get('max_attempts', 1))
        if attempts < 1 or attempts > 3:
            attempts = 1
    except:
        attempts = 1

    try:
        result = solve_turnstile_token(url, max_attempts=attempts, proxy=proxy)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
