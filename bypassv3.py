import os
import re
import json
import requests
from urllib.parse import urlparse, parse_qs
from flask import Flask, request, jsonify
from BypassTurns import solve_turnstile_token

app = Flask(__name__)


def extract_params_from_url(url):
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    return {k: v[0] if v else '' for k, v in params.items()}


def get_anchor_page(session, recaptcha_url_get):
    response = session.get(recaptcha_url_get)
    return response.text


def reload_recaptcha(session, recaptcha_url_get, recaptcha_url_post, token):
    params = extract_params_from_url(recaptcha_url_get)

    data = {
        'v': params.get('v', ''),
        'reason': 'q',
        'threat': '0',
        'c': token,
        'k': params.get('k', ''),
        'co': params.get('co', ''),
        'hl': params.get('hl', ''),
        'size': params.get('size', '')
    }

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': 'https://www.google.com/',
        'Origin': 'https://www.google.com'
    }

    response = session.post(recaptcha_url_post, data=data, headers=headers)
    return response.text


def extract_recaptcha_token(response_text):
    patterns = [
        r'"rresp","([^"]+)"',
        r'"token":"([^"]+)"',
        r'"recaptcha-token":"([^"]+)"',
        r'token=([^&]+)',
        r'response=([^&]+)',
        r'\["rresp","([^"]+)"\]'
    ]

    for pattern in patterns:
        match = re.search(pattern, response_text)
        if match:
            return match.group(1)

    try:
        data = json.loads(response_text)
        if 'token' in data:
            return data['token']
        if 'rresp' in data:
            return data['rresp']
    except:
        pass

    token_pattern = r'[A-Za-z0-9_-]{100,}'
    matches = re.findall(token_pattern, response_text)
    if matches:
        return max(matches, key=len)

    return None


def solve_recaptcha(recaptcha_url_get, recaptcha_url_post):
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    })

    anchor_response = get_anchor_page(session, recaptcha_url_get)
    token = extract_recaptcha_token(anchor_response)
    if not token:
        return None
    reload_response = reload_recaptcha(session, recaptcha_url_get, recaptcha_url_post, token)
    new_token = extract_recaptcha_token(reload_response)
    return new_token if new_token else token


@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'api': 'recaptcha-solver',
        'usage': 'POST /solve com JSON: {"recaptcha_url_get": "...", "recaptcha_url_post": "..."}'
    })


@app.route('/solve', methods=['POST'])
def solve():
    data = request.get_json(silent=True) or {}

    recaptcha_url_get = data.get('recaptcha_url_get')
    recaptcha_url_post = data.get('recaptcha_url_post')

    if not recaptcha_url_get or not recaptcha_url_post:
        return jsonify({
            'success': False,
            'error': 'Campos obrigatorios: recaptcha_url_get e recaptcha_url_post'
        }), 400

    try:
        token = solve_recaptcha(recaptcha_url_get, recaptcha_url_post)
        return jsonify({'success': bool(token), 'token': token})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/solve-turnstile', methods=['POST'])
def solve_turnstile():
    data = request.get_json(silent=True) or {}

    url = data.get('url')
    if not url:
        return jsonify({
            'success': False,
            'error': 'Campo obrigatorio: url'
        }), 400

    if not url.startswith('http'):
        url = 'https://' + url

    try:
        result = solve_turnstile_token(url)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
