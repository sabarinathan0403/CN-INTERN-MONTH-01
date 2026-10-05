import os, csv, time
from datetime import datetime
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

URL = "https://coinmarketcap.com/"
TOP_N = 10
HEADLESS = True
SNAPSHOT_CSV = "crypto_prices.csv"
HISTORY_CSV = "crypto_price_history.csv"
FILTER_ENABLED = False
FILTER_MODE = "top_gainers"   # "price_above" or "top_gainers"
PRICE_THRESHOLD = 100.0
TOP_GAINERS_COUNT = 3

def parse_num(value: str) -> float:
    """Parse '$1.6T', '$304.57B', '$63,215.12' into a float."""
    try:
        c = value.replace("$", "").replace(",", "").strip().upper()
        mult = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
        return float(c[:-1]) * mult[c[-1]] if c and c[-1] in mult else float(c)
    except ValueError:
        return 0.0

def parse_pct(value: str) -> float:
    try:
        return float(value.replace("%", "").replace("+", "").strip())
    except ValueError:
        return 0.0

def get_driver():
    opts = Options()
    opts.page_load_strategy = "eager"
    if HEADLESS:
        opts.add_argument("--headless=new")
    for a in ["--window-size=1920,1080", "--disable-gpu", "--no-sandbox",
              "--disable-dev-shm-usage", "--remote-allow-origins=*",
              "--disable-blink-features=AutomationControlled"]:
        opts.add_argument(a)
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    driver.set_page_load_timeout(60)
    return driver

def scrape_coins(driver) -> list[dict]:
    driver.get(URL)
    WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
    time.sleep(2)
    coins = []
    for row in driver.find_elements(By.CSS_SELECTOR, "table tbody tr"):
        if len(coins) >= TOP_N:
            break
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) < 9:
            continue
        name_block = cells[2].text.strip().split("\n")
        name = name_block[0]
        symbol = name_block[1] if len(name_block) > 1 else ""
        price, change_24h, cap = cells[3].text.strip(), cells[5].text.strip(), cells[7].text.strip()
        if not symbol or parse_num(price) <= 0 or parse_num(cap) <= 0:
            continue
        coins.append({"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                       "name": name, "symbol": symbol, "price": price,
                       "change_24h": change_24h, "market_cap": cap})
    return coins

def apply_filter(data: list[dict]) -> list[dict]:
    if not FILTER_ENABLED:
        return data
    if FILTER_MODE == "price_above":
        return [d for d in data if parse_num(d["price"]) > PRICE_THRESHOLD]
    if FILTER_MODE == "top_gainers":
        return sorted(data, key=lambda d: parse_pct(d["change_24h"]), reverse=True)[:TOP_GAINERS_COUNT]
    return data

def save_csv(data: list[dict]):
    pd.DataFrame(data).to_csv(SNAPSHOT_CSV, index=False)
    exists = os.path.isfile(HISTORY_CSV)
    with open(HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp", "name", "symbol", "price", "change_24h", "market_cap"])
        if not exists:
            w.writeheader()
        w.writerows(data)

def main():
    driver = get_driver()
    try:
        data = scrape_coins(driver)
        if not data:
            print("No data scraped — CoinMarketCap's layout may have changed.")
            return
        for c in (apply_filter(data) if FILTER_ENABLED else data):
            print(f"{c['name']} ({c['symbol']}): {c['price']} | 24h: {c['change_24h']} | Cap: {c['market_cap']}")
        save_csv(data)
        print(f"\nSaved {SNAPSHOT_CSV} and appended to {HISTORY_CSV}.")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
#python crypto_tracker_compact.py