

import time
import json
import re
import sys
import os
import socket
import threading
import tempfile
import random
import base64
import subprocess
import http.client
from urllib.parse import urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import undetected_chromedriver as uc

HEADLESS = os.environ.get('HEADLESS', '0') == '1'
CHROME_BIN = os.environ.get('CHROME_BIN')
CHROMEDRIVER_BIN = os.environ.get('CHROMEDRIVER_BIN')


class Config:
    HUMAN_TYPING_SPEED_MIN = 0.05
    HUMAN_TYPING_SPEED_MAX = 0.25
    HUMAN_MOUSE_SPEED_MIN = 0.3
    HUMAN_MOUSE_SPEED_MAX = 1.2
    HUMAN_SCROLL_PAUSE_MIN = 1.5
    HUMAN_SCROLL_PAUSE_MAX = 3.5
    SCREEN_WIDTH = 1366
    SCREEN_HEIGHT = 768

def get_chrome_version():
    try:
        if CHROME_BIN and os.path.exists(CHROME_BIN):
            output = subprocess.check_output([CHROME_BIN, '--version'], encoding='utf-8')
            match = re.search(r'(\d+)\.', output.strip())
            if match:
                return int(match.group(1))

        if os.name == 'nt':
            paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ]
            for path in paths:
                if os.path.exists(path):
                    output = subprocess.check_output(
                        ['powershell', '-Command', f"(Get-Item '{path}').VersionInfo.ProductVersion"],
                        encoding='utf-8'
                    )
                    match = re.search(r'(\d+)\.', output.strip())
                    if match:
                        return int(match.group(1))

        for cmd in (['google-chrome', '--version'], ['chromium', '--version'], ['chromium-browser', '--version']):
            try:
                output = subprocess.check_output(cmd, encoding='utf-8')
                version = re.search(r'(\d+)\.', output.strip())
                if version:
                    return int(version.group(1))
            except:
                continue
    except:
        pass

    print("[!] Nao foi possivel detectar versao do Chrome. Usando 120")
    return 120

class LocalProxy:
    def __init__(self, upstream_url):
        parsed = urlparse(upstream_url)
        self.upstream_host = parsed.hostname
        self.upstream_port = parsed.port or 80
        self.auth = None
        if parsed.username:
            raw = f"{parsed.username}:{parsed.password or ''}"
            self.auth = f"Basic {base64.b64encode(raw.encode()).decode()}"

    def _forward_http(self, method, path, headers, body, sock):
        conn = http.client.HTTPConnection(self.upstream_host, self.upstream_port, timeout=60)
        try:
            fwd = {k: v for k, v in headers.items() if k.lower() != 'proxy-authorization'}
            if self.auth:
                fwd['Proxy-Authorization'] = self.auth
            conn.request(method, path, body=body, headers=fwd)
            resp = conn.getresponse()
            data = resp.read()
            sock.sendall(f"HTTP/1.1 {resp.status} {resp.reason}\r\n".encode())
            skip = {'transfer-encoding', 'connection', 'proxy-authenticate'}
            for k, v in resp.getheaders():
                if k.lower() not in skip:
                    sock.sendall(f"{k}: {v}\r\n".encode())
            sock.sendall(f"Content-Length: {len(data)}\r\n\r\n".encode())
            sock.sendall(data)
        finally:
            conn.close()

    def handle(self, sock, addr):
        try:
            sock.settimeout(30)
            f = sock.makefile('rb')
            request_line = f.readline()
            if not request_line:
                return
            parts = request_line.decode('latin-1', 'replace').strip().split()
            if len(parts) < 3:
                return
            method, path, version = parts[0], parts[1], parts[2]

            headers = {}
            while True:
                line = f.readline()
                if not line or line in (b'\r\n', b'\n'):
                    break
                key, _, value = line.decode('latin-1', 'replace').partition(':')
                headers[key.strip().lower()] = value.strip()

            if method == 'CONNECT':
                self._handle_connect(sock, path)
                return

            length = int(headers.get('content-length', '0') or 0)
            body = f.read(length) if length else None
            self._forward_http(method, path, headers, body, sock)
        except Exception:
            try:
                sock.close()
            except Exception:
                pass

    def _handle_connect(self, sock, target):
        try:
            upstream = socket.create_connection((self.upstream_host, self.upstream_port), timeout=60)
            req = f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n"
            if self.auth:
                req += f"Proxy-Authorization: {self.auth}\r\n"
            req += "\r\n"
            upstream.sendall(req.encode())

            resp = b""
            while b"\r\n\r\n" not in resp:
                chunk = upstream.recv(4096)
                if not chunk:
                    break
                resp += chunk
                if len(resp) > 65536:
                    break

            if b" 200 " not in resp.split(b"\r\n")[0]:
                sock.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
                upstream.close()
                return

            sock.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")

            def pipe(src, dst):
                try:
                    while True:
                        data = src.recv(65536)
                        if not data:
                            break
                        dst.sendall(data)
                except Exception:
                    pass
                finally:
                    try:
                        dst.shutdown(socket.SHUT_WR)
                    except Exception:
                        pass

            t1 = threading.Thread(target=pipe, args=(sock, upstream), daemon=True)
            t2 = threading.Thread(target=pipe, args=(upstream, sock), daemon=True)
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            upstream.close()
        except Exception:
            try:
                sock.close()
            except Exception:
                pass


def start_local_proxy(upstream_url):
    import socket as _s
    server = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
    server.bind(('127.0.0.1', 0))
    server.listen(50)
    server.settimeout(1)
    port = server.getsockname()[1]
    proxy = LocalProxy(upstream_url)
    running = {'stop': False}

    def acceptor():
        while not running['stop']:
            try:
                conn, addr = server.accept()
                threading.Thread(target=proxy.handle, args=(conn, addr), daemon=True).start()
            except Exception:
                if running['stop']:
                    break
    threading.Thread(target=acceptor, daemon=True).start()
    return running, port


class TurnstileSolver:
    def __init__(self, url, proxy=None):
        self.url = url
        self.proxy = proxy
        self.local_proxy = None
        self.driver = None
        self.token = None
        self.cf_clearance = None
        self.chrome_version = get_chrome_version()

    def setup_driver(self):
        print(f"[*] Versao do Chrome detectada: {self.chrome_version}")
        print("[*] Configurando navegador...")

        options = uc.ChromeOptions()
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument(f'--window-size={Config.SCREEN_WIDTH},{Config.SCREEN_HEIGHT}')
        options.add_argument('--accept-lang=pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7')

        if HEADLESS:
            options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-background-networking')
            options.add_argument('--disable-component-update')
            options.add_argument('--disable-default-apps')
            options.add_argument('--disable-sync')
            options.add_argument('--metrics-recording-only')
            options.add_argument('--mute-audio')
            options.add_argument('--disable-software-rasterizer')
            options.add_argument('--no-first-run')
            options.add_argument('--disable-features=TranslateUI,AutofillServerCommunication,CalculateNativeWinOcclusion,MediaRouter')
            options.add_argument(
                f'--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                f'AppleWebKit/537.36 (KHTML, like Gecko) '
                f'Chrome/{self.chrome_version}.0.0.0 Safari/537.36'
            )

        if self.proxy:
            parsed = urlparse(self.proxy)
            proxy_arg = self.proxy
            if parsed.username:
                self.local_proxy = start_local_proxy(self.proxy)
                proxy_arg = f"http://127.0.0.1:{self.local_proxy[1]}"
                print(f"[*] Proxy local em {proxy_arg} -> {parsed.hostname}:{parsed.port}")
            else:
                print(f"[*] Usando proxy: {parsed.hostname}:{parsed.port}")
            options.add_argument(f'--proxy-server={proxy_arg}')

        kwargs = {'version_main': self.chrome_version}
        if CHROME_BIN:
            kwargs['browser_executable_path'] = CHROME_BIN
        if CHROMEDRIVER_BIN:
            kwargs['driver_executable_path'] = CHROMEDRIVER_BIN

        print(f"[*] Criando driver para Chrome {self.chrome_version}...")

        try:
            self.driver = uc.Chrome(options=options, **kwargs)
        except Exception as e:
            print(f"[X] Erro ao criar driver: {e}")
            fallback_options = uc.ChromeOptions()
            fallback_options.add_argument('--disable-blink-features=AutomationControlled')
            if HEADLESS:
                fallback_options.add_argument('--headless=new')
                fallback_options.add_argument('--no-sandbox')
                fallback_options.add_argument('--disable-dev-shm-usage')
            self.driver = uc.Chrome(options=fallback_options, **kwargs)

        self.driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        self.driver.execute_cdp_cmd('Browser.getWindowForTarget', {})
        self.driver.set_script_timeout(45)
        if not HEADLESS:
            self.driver.minimize_window()
        print("[OK] Navegador pronto!")

    def solve_turnstile(self):
        try:
            self.setup_driver()

            print(f"[*] Acessando: {self.url}")
            self.driver.get(self.url)

            print("[*] Aguardando carregamento da pagina...")
            time.sleep(random.uniform(2.5, 4))

            current_url = self.driver.current_url
            page_title = self.driver.title
            print(f"[OK] Pagina carregada: {page_title}")

            print("[*] Simulando navegacao humana...")
            self._simulate_human()

            print("[*] Aguardando API do Turnstile...")
            self._wait_for_turnstile_api()

            print("[*] Resolvendo Turnstile via JS...")
            self._solve_via_js()

            print("[*] Aguardando bypass...")
            time.sleep(random.uniform(2, 3))

            self._extract_tokens()

            if self.token:
                print("[OK] TURNSTILE BYPASSADO COM SUCESSO!")
                return True
            else:
                print("[X] Nao foi possivel obter o token")
                return False

        except Exception as e:
            print(f"[X] Erro critico: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _wait_for_turnstile_api(self):
        for i in range(10):
            try:
                ok = self.driver.execute_script(
                    "return typeof turnstile !== 'undefined' "
                    "&& document.querySelector('.cf-turnstile, [data-sitekey]') !== null"
                )
                if ok:
                    print("[OK] API e widget Turnstile prontos")
                    return
            except:
                pass
            time.sleep(2)
        print("[!] API do Turnstile nao detectada")

    def _solve_via_js(self):
        try:
            self.driver.execute_script("""
                window.__tsErr = null;
                var w = document.querySelectorAll('.cf-turnstile, [data-sitekey]');
                for (var i = 0; i < w.length; i++) {
                    try {
                        turnstile.render(w[i], {
                            'error-callback': function (e) { window.__tsErr = String(e); }
                        });
                    }
                    catch (e) {
                        try { turnstile.execute(w[i]); } catch (e2) {}
                    }
                }
            """)
            time.sleep(2)

            token = self.driver.execute_async_script("""
                var done = arguments[arguments.length - 1];
                function getToken() {
                    try {
                        var t = turnstile.getResponse();
                        if (t && t.length > 20) return t;
                    } catch (e) {}
                    var inputs = document.querySelectorAll('input[name="cf-turnstile-response"]');
                    for (var i = 0; i < inputs.length; i++) {
                        if (inputs[i].value && inputs[i].value.length > 20) return inputs[i].value;
                    }
                    return null;
                }
                var start = Date.now();
                function poll() {
                    var t = getToken();
                    if (t) { done(t); return; }
                    if (Date.now() - start > 15000) { done(null); return; }
                    setTimeout(poll, 1000);
                }
                poll();
            """)
            if token:
                self.token = token
                print(f"[OK] Token obtido via JS: {token[:50]}...")
            else:
                err = self.driver.execute_script("return window.__tsErr || null;")
                if err:
                    print(f"[!] Erro do widget Turnstile: {err}")
        except Exception as e:
            print(f"[!] Erro no solve via JS: {e}")

    def _simulate_human(self):
        try:
            for _ in range(random.randint(2, 4)):
                scroll_amount = random.randint(100, 500)
                self.driver.execute_script(f"window.scrollBy(0, {scroll_amount})")
                time.sleep(random.uniform(0.5, 1.5))

            actions = ActionChains(self.driver)
            for _ in range(random.randint(3, 5)):
                try:
                    x = random.randint(100, Config.SCREEN_WIDTH - 100)
                    y = random.randint(100, Config.SCREEN_HEIGHT - 100)
                    actions.move_by_offset(x, y)
                    actions.perform()
                    time.sleep(random.uniform(0.2, 0.5))
                except:
                    pass

            time.sleep(random.uniform(1, 2))

        except Exception as e:
            print(f"[!] Erro na simulacao: {e}")

    def _handle_turnstile(self):
        try:
            print("[!] Aguardando Turnstile carregar...")
            time.sleep(random.uniform(3, 6))

            turnstile_found = False

            try:
                cf_container = self.driver.find_elements(By.CSS_SELECTOR,
                    "[class*='cf-turnstile'], [id*='cf-turnstile'], [data-sitekey]")
                if cf_container:
                    turnstile_found = True
                    print("[OK] Container cf-turnstile encontrado!")

                    for container in cf_container:
                        try:
                            inner_iframes = container.find_elements(By.TAG_NAME, "iframe")
                            if not inner_iframes:
                                print("[*] Aguardando iframe dentro do container...")
                                time.sleep(5)
                                inner_iframes = container.find_elements(By.TAG_NAME, "iframe")
                            if inner_iframes:
                                iframe = inner_iframes[0]
                                print("[OK] Turnstile iframe dentro do container!")
                                self._interact_with_iframe(iframe)
                                break
                            else:
                                print("[*] Sem iframe no container, tentando pai...")
                                parent = self.driver.execute_script(
                                    "return arguments[0].parentElement;", container)
                                if parent:
                                    parent_iframes = parent.find_elements(By.TAG_NAME, "iframe")
                                    if parent_iframes:
                                        print("[OK] Iframe encontrado no pai!")
                                        self._interact_with_iframe(parent_iframes[0])
                                        break
                        except Exception as e2:
                            print(f"[!] Erro no container: {e2}")
            except:
                pass

            if not turnstile_found:
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    try:
                        src = (iframe.get_attribute('src') or '').lower()
                        id_attr = (iframe.get_attribute('id') or '').lower()
                        name_attr = (iframe.get_attribute('name') or '').lower()
                        cls = (iframe.get_attribute('class') or '').lower()

                        is_turnstile = any(x in src or x in id_attr or x in name_attr or x in cls
                            for x in ['cloudflare', 'turnstile', 'challenges', 'cf-', 'captcha'])
                        if not is_turnstile:
                            size = iframe.size
                            if size.get('width', 0) > 200 and size.get('height', 0) > 50 and size.get('height', 0) < 200:
                                is_turnstile = True

                        if is_turnstile:
                            turnstile_found = True
                            print(f"[OK] Turnstile iframe detectado (src={src[:60]})")
                            self._interact_with_iframe(iframe)
                            break
                    except:
                        continue

            if not turnstile_found:
                print("[!] Turnstile nao encontrado visualmente")
                page_source = self.driver.page_source.lower()
                if 'cf-turnstile' in page_source:
                    print("[OK] cf-turnstile encontrado no HTML, tentando via JS...")
                    try:
                        self.driver.execute_script("""
                            var w = document.querySelector('[class*="cf-turnstile"]');
                            if (w) { w.click(); }
                        """)
                        time.sleep(3)
                    except:
                        pass

        except Exception as e:
            print(f"[!] Erro no Turnstile: {e}")
            try:
                self.driver.switch_to.default_content()
            except:
                pass

    def _interact_with_iframe(self, iframe):
        try:
            self.driver.switch_to.frame(iframe)
            print("[*] Dentro do iframe, procurando checkbox...")
            time.sleep(2)

            clicked = False
            selectors = [
                "input[type='checkbox']",
                "[role='checkbox']",
                ".mark",
                "label",
                "#challenge-stage input",
                "#challenge-stage label",
                "body",
            ]
            for sel in selectors:
                try:
                    elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for elem in elems:
                        if elem.is_displayed():
                            self.driver.execute_script("arguments[0].click();", elem)
                            print(f"[OK] Clique realizado em: {sel}")
                            clicked = True
                            break
                    if clicked:
                        break
                except:
                    continue

            if not clicked:
                try:
                    body = self.driver.find_element(By.TAG_NAME, "body")
                    actions = ActionChains(self.driver)
                    actions.move_to_element(body).pause(0.5).click().perform()
                    print("[OK] Clique via ActionChains no body")
                except:
                    pass

            time.sleep(random.uniform(2, 4))
            self.driver.switch_to.default_content()
            print("[OK] Saiu do iframe")
        except Exception as e:
            print(f"[!] Erro ao interagir com iframe: {e}")
            try:
                self.driver.switch_to.default_content()
            except:
                pass

    def _extract_tokens(self):
        for attempt in range(3):
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR,
                    "input[name='cf-turnstile-response']")
                for elem in elements:
                    val = elem.get_attribute('value')
                    if val and len(val) > 10:
                        self.token = val
                        print(f"[OK] Token: {val[:50]}...")
                        break

                if not self.token:
                    self.token = self.driver.execute_script("""
                        var inputs = document.querySelectorAll('input[name="cf-turnstile-response"]');
                        for (var i = 0; i < inputs.length; i++) {
                            if (inputs[i].value && inputs[i].value.length > 10) return inputs[i].value;
                        }
                        return null;
                    """)
                    if self.token:
                        print(f"[OK] Token via JS: {self.token[:50]}...")

                if self.token:
                    break

                if attempt < 2:
                    print("[!] Token nao encontrado ainda, aguardando...")
                    time.sleep(3)

            except Exception as e:
                print(f"[!] Erro na extracao: {e}")

            try:
                cookies = self.driver.get_cookies()
                for cookie in cookies:
                    if cookie['name'] == 'cf_clearance':
                        self.cf_clearance = cookie['value']
                        print(f"[OK] CF Clearance: {self.cf_clearance[:50]}...")
                    if 'cf_' in cookie['name'] or 'turnstile' in cookie['name'].lower():
                        print(f"[OK] Cookie: {cookie['name']} = {cookie['value'][:30]}...")
            except:
                pass

    def get_tokens(self):
        if not self.driver:
            return {}

        try:
            return {
                'turnstile_token': self.token,
                'cf_clearance': self.cf_clearance,
                'cookies': self.driver.get_cookies(),
                'user_agent': self.driver.execute_script("return navigator.userAgent;"),
                'page_url': self.driver.current_url
            }
        except:
            return {'turnstile_token': None, 'cf_clearance': None, 'cookies': []}

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
                print("[*] Navegador fechado")
            except:
                pass
            self.driver = None
        if self.local_proxy:
            try:
                self.local_proxy[0]['stop'] = True
            except:
                pass
            self.local_proxy = None

def run_bypass(url, verbose=True):
    if verbose:
        print("=" * 50)
        print("[*] Iniciando bypass do Turnstile")
        print(f"[*] URL: {url}")
        print("=" * 50)
        print()

    solver = TurnstileSolver(url)
    solver.solve_turnstile()
    tokens = solver.get_tokens()

    if verbose:
        with open('tokens.json', 'w', encoding='utf-8') as f:
            json.dump(tokens, f, indent=2, default=str, ensure_ascii=False)
        print()
        print("=" * 50)
        print("[OK] PROCESSO CONCLUIDO!")
        print("=" * 50)
        print()
        print("Tokens extraidos:")
        print(f"Turnstile Token: {tokens.get('turnstile_token') or 'Nao encontrado'}")
        print(f"CF Clearance: {tokens.get('cf_clearance') or 'Nao encontrado'}")
        print(f"Cookies capturados: {len(tokens.get('cookies', []))}")

    solver.close()
    return tokens

def solve_turnstile_token(url, max_attempts=1, proxy=None):
    last = {
        'success': False,
        'turnstile_token': None,
        'cf_clearance': None,
    }
    for attempt in range(max_attempts):
        solver = TurnstileSolver(url, proxy=proxy)
        try:
            ok = solver.solve_turnstile()
            tokens = solver.get_tokens()
            last = {
                'success': ok,
                'turnstile_token': tokens.get('turnstile_token'),
                'cf_clearance': tokens.get('cf_clearance'),
            }
        finally:
            solver.close()
        if last.get('turnstile_token'):
            break
        if attempt < max_attempts - 1:
            print(f"[!] Tentativa {attempt + 1} sem token, tentando de novo...")
            time.sleep(3)
    return last

def main():
    print("[?] Digite a URL do site com Turnstile:")
    url = input(">>> ").strip()
    if not url:
        print("[X] URL invalida!")
        sys.exit(1)
    if not url.startswith('http'):
        url = 'https://' + url
    run_bypass(url)

if __name__ == '__main__':
    main()
