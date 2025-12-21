# pip install selenium webdriver-manager pandas
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ---------- CONFIG ----------
LOGIN_URL = "https://acc.otithee.com/login"
CHANGE_REFERER_URL = "https://acc.otithee.com/change-referer"
USERNAME = "needyamin@otithee.com"
PASSWORD = "Y123456789"
INPUT_CSV = "data.csv"
OUTPUT_CSV = "results.csv"
HEADLESS = False   # True to run without opening Chrome window
# ----------------------------

def setup_driver():
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_window_size(1200, 900)
    return driver

def login(driver):
    wait = WebDriverWait(driver, 20)
    driver.get(LOGIN_URL)

    # Fill username/email
    user_elem = wait.until(EC.presence_of_element_located((By.NAME, "email")))
    user_elem.clear()
    user_elem.send_keys(USERNAME)

    # Fill password
    pwd_elem = driver.find_element(By.NAME, "password")
    pwd_elem.clear()
    pwd_elem.send_keys(PASSWORD)

    # Click login button (AJAX/jQuery submit)
    login_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.auth-form-btn")))
    driver.execute_script("arguments[0].click();", login_btn)

    # Wait for navigation or some change that indicates login success.
    # Prefer URL change, but fallback to presence of element on the logged-in page.
    try:
        wait.until(lambda d: d.current_url != LOGIN_URL)
    except:
        # fallback: wait for entrepreneurNumber or other dashboard marker (may appear after redirect)
        try:
            wait.until(EC.presence_of_element_located((By.ID, "entrepreneurNumber")))
        except:
            # if both fail, proceed anyway (login may have succeeded but UI differs)
            pass

def inject_network_monitor(driver):
    """Injects a small monitor that increments window.__activeRequests for fetch and XHR."""
    script = """
    if (!window.__networkMonitorInjected) {
      window.__networkMonitorInjected = true;
      window.__activeRequests = 0;
      (function(){
        // instrument fetch
        try {
          if (window.fetch) {
            var _fetch = window.fetch.bind(window);
            window.fetch = function() {
              try { window.__activeRequests++; } catch(e) {}
              try {
                var p = _fetch.apply(this, arguments);
                if (p && p.then) {
                  return p.then(function(res){ try{ window.__activeRequests = Math.max(0, window.__activeRequests - 1);}catch(e){}; return res; })
                          .catch(function(err){ try{ window.__activeRequests = Math.max(0, window.__activeRequests - 1);}catch(e){}; throw err; });
                }
                return p;
              } catch(err) {
                try{ window.__activeRequests = Math.max(0, window.__activeRequests - 1);}catch(e){}
                throw err;
              }
            };
          }
        } catch(e) {}

        // instrument XHR
        try {
          if (window.XMLHttpRequest) {
            var _open = XMLHttpRequest.prototype.open;
            var _send = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open = function() {
              try { this.__url = arguments[1]; } catch(e){}
              return _open.apply(this, arguments);
            };
            XMLHttpRequest.prototype.send = function() {
              var xhr = this;
              try { window.__activeRequests++; } catch(e){}
              var onreadystatechange = xhr.onreadystatechange;
              xhr.onreadystatechange = function() {
                try {
                  if (xhr.readyState === 4) {
                    window.__activeRequests = Math.max(0, window.__activeRequests - 1);
                  }
                } catch(e) {}
                if (onreadystatechange) {
                  return onreadystatechange.apply(this, arguments);
                }
              };
              try {
                return _send.apply(this, arguments);
              } catch(err) {
                try { window.__activeRequests = Math.max(0, window.__activeRequests - 1); } catch(e) {}
                throw err;
              }
            };
          }
        } catch(e) {}
      })();
    }
    """
    driver.execute_script(script)

def _get_active_requests(driver):
    try:
        return int(driver.execute_script("return (typeof window.__activeRequests === 'undefined') ? 0 : window.__activeRequests;"))
    except:
        return 0

def submit_one(driver, entrepreneur_num, referer_num):
    wait = WebDriverWait(driver, 40)
    driver.get(CHANGE_REFERER_URL)

    # Wait for form ready
    wait.until(EC.presence_of_element_located((By.ID, "entrepreneurNumber")))
    inject_network_monitor(driver)   # inject monitor BEFORE triggering AJAX

    ent = driver.find_element(By.ID, "entrepreneurNumber")
    ref = driver.find_element(By.ID, "entrepreneurReferer")

    # Normalize numbers with leading 0
    entrepreneur_num = "0" + str(entrepreneur_num).lstrip("0")
    referer_num = "0" + str(referer_num).lstrip("0")

    # --- Step 1: Type entrepreneurNumber (this triggers API) ---
    ent.clear()
    ent.send_keys(entrepreneur_num)

    # --- Step 2: Wait for network activity to finish and form to be populated ---
    def ajax_populated(driver_inner):
        # 1) If network monitor exists and activeRequests > 0 -> still busy
        active = _get_active_requests(driver_inner)
        if active > 0:
            return False

        # 2) If there's an element 'entrepreneurName' and it has non-empty value -> consider populated
        try:
            elem = driver_inner.find_element(By.ID, "entrepreneurName")
            if elem.get_attribute("value") and elem.get_attribute("value").strip() != "":
                return True
        except:
            pass

        # 3) If referer input becomes enabled (not readonly/disabled) -> consider populated
        try:
            ref_el = driver_inner.find_element(By.ID, "entrepreneurReferer")
            readonly = ref_el.get_attribute("readonly")
            disabled = ref_el.get_attribute("disabled")
            if ref_el.is_enabled() and not readonly and not disabled:
                return True
        except:
            pass

        # 4) If no recognizable loader exists and active==0 we accept it
        try:
            loaders = driver_inner.find_elements(By.CSS_SELECTOR, ".spinner-border, .loading, .loader, .ajax-loader")
            visible_loader = any([l.is_displayed() for l in loaders])
            if not visible_loader and active == 0:
                return True
        except:
            pass

        return False

    # Wait until our ajax_populated returns True or timeout
    try:
        wait.until(ajax_populated)
    except Exception:
        # final fallback: ensure network is idle (monitor==0) even if page signals failed
        try:
            WebDriverWait(driver, 10).until(lambda d: _get_active_requests(d) == 0)
        except:
            # give up and continue (we'll likely get a failure message on submit)
            pass

    # --- Step 3: Now safe to input referer ---
    try:
        ref.clear()
        ref.send_keys(referer_num)
    except Exception as e:
        return False, f"Failed to input referer: {e}"

    # --- Step 4: Submit form ---
    try:
        submit_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "form#entrepreneurForm button")))
        driver.execute_script("arguments[0].click();", submit_btn)
    except Exception as e:
        return False, f"Failed to click submit: {e}"

    # --- Step 5: Wait for final response (outputResponse or flash messages) and ensure network idle ---
    try:
        wait.until(
            lambda d: (
                (d.find_elements(By.ID, "outputResponse") and d.find_element(By.ID, "outputResponse").get_attribute("value").strip() != "")
                or any(el.is_displayed() and el.text.strip() for el in d.find_elements(By.CSS_SELECTOR, ".alert, .toast, .text-danger, .text-success"))
            )
        )
        # ensure final network calls finished
        WebDriverWait(driver, 20).until(lambda d: _get_active_requests(d) == 0)

        out_val = ""
        try:
            out_val = driver.find_element(By.ID, "outputResponse").get_attribute("value").strip()
        except:
            pass

        if out_val:
            return True, out_val
        else:
            try:
                flash = driver.find_element(By.CSS_SELECTOR, ".alert, .toast, .text-danger, .text-success")
                return True, flash.text.strip()[:1000]
            except:
                return False, "No response text found after submit."
    except Exception as e:
        # try to capture any flash message as last resort
        try:
            flash = driver.find_element(By.CSS_SELECTOR, ".alert, .toast, .text-danger, .text-success")
            return True, flash.text.strip()[:1000]
        except:
            return False, f"No response detected (exception: {e})"

def main():
    df = pd.read_csv(INPUT_CSV, dtype=str).fillna("")
    if not {"entrepreneurNumber", "refererNumber"}.issubset(df.columns):
        raise SystemExit("CSV must contain columns: entrepreneurNumber, refererNumber")

    driver = setup_driver()
    try:
        login(driver)
        results = []

        for idx, row in df.iterrows():
            ent = row['entrepreneurNumber']
            ref = row['refererNumber']
            try:
                ok, resp = submit_one(driver, ent, ref)
                status = "ok" if ok else "failed"
            except Exception as e:
                status = "error"
                resp = str(e)

            print(f"[{idx}] {ent} -> {ref} => {status}")
            results.append({
                "entrepreneurNumber": "0" + str(ent).lstrip("0"),
                "refererNumber": "0" + str(ref).lstrip("0"),
                "status": status,
                "response": resp
            })

        pd.DataFrame(results).to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        print("All done. Results saved to", OUTPUT_CSV)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
