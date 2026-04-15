import undetected_chromedriver as uc
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By


def get_driver():
    options = uc.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--window-size=1280,800")
    options.add_argument("--lang=en-US")
    options.add_argument("--log-level=3")
    driver = uc.Chrome(options=options)
    return driver


def wait_for(driver, css_selector, timeout=25):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
    )