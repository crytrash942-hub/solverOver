

import time
import json
import re
import sys
import os
import random
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import undetected_chromedriver as uc


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

        output = subprocess.check_output(['google-chrome', '--version'], encoding='utf-8')
        version = re.search(r'(\d+)\.', output)
        if version:
            return int(version.group(1))
    except:
        pass

    print("[!] Nao foi possivel detectar versao do Chrome. Usando 120")
    return 120

class TurnstileSolver:
    def __init__(self, url):
        self.url = url
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

        print(f"[*] Criando driver para Chrome {self.chrome_version}...")

        try:
            self.driver = uc.Chrome(options=options, version_main=self.chrome_version)
        except Exception as e:
            print(f"[X] Erro ao criar driver: {e}")
            fallback_options = uc.ChromeOptions()
            fallback_options.add_argument('--disable-blink-features=AutomationControlled')
            self.driver = uc.Chrome(options=fallback_options)

        self.driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        self.driver.execute_cdp_cmd('Browser.getWindowForTarget', {})
        self.driver.minimize_window()
        print("[OK] Navegador pronto!")

    def solve_turnstile(self):
        try:
            self.setup_driver()

            print(f"[*] Acessando: {self.url}")
            self.driver.get(self.url)

            print("[*] Aguardando carregamento da pagina...")
            time.sleep(random.uniform(5, 8))

            current_url = self.driver.current_url
            page_title = self.driver.title
            print(f"[OK] Pagina carregada: {page_title}")

            print("[*] Simulando navegacao humana...")
            self._simulate_human()

            print("[*] Verificando Turnstile...")
            self._handle_turnstile()

            print("[*] Aguardando bypass...")
            time.sleep(random.uniform(5, 10))

            self._extract_tokens()

            if self.token or self.cf_clearance:
                print("[OK] TURNSTILE BYPASSADO COM SUCESSO!")
                return True
            else:
                print("[OK] Bypass aparentemente concluido (verifique manualmente)")
                return True

        except Exception as e:
            print(f"[X] Erro critico: {e}")
            import traceback
            traceback.print_exc()
            return False

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
