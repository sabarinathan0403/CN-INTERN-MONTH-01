import time
import csv
import json
import random
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
TOP_250_URL = "https://www.imdb.com/chart/top/"
HEADLESS = True                 # Set False if you want to see the browser
MAX_MOVIES = 250                # Lower this (e.g. 10) for quick testing
SCRAPE_CAST_AND_GENRE = True    # Set False to skip visiting each movie page (much faster)
CAST_LIMIT = 5                  # Number of top-billed cast members to keep
OUTPUT_CSV = "imdb_top_movies.csv"
REQUEST_DELAY_RANGE = (1.0, 2.0)  # Random delay (seconds) between page visits
def build_driver(headless: bool = True) -> webdriver.Chrome:
    """Create and return a configured Chrome WebDriver instance."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=en-US")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
    # Reduce obvious signs of automation, which some sites use to block scrapers
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver
def dismiss_cookie_banner(driver: webdriver.Chrome):
    """Best-effort dismissal of IMDb's cookie-consent overlay, if present."""
    possible_selectors = [
        "button[data-testid='accept-button']",
        "#onetrust-accept-btn-handler",
        "button[aria-label='Accept']",
    ]
    for sel in possible_selectors:
        try:
            btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
            btn.click()
            time.sleep(0.5)
            return
        except Exception:
            continue  # No banner found with this selector, try the next / give up silently
def get_ld_json_blocks(driver: webdriver.Chrome) -> list:
    """Return a list of parsed JSON objects from every ld+json script tag on the page."""
    scripts = driver.find_elements(By.CSS_SELECTOR, "script[type='application/ld+json']")
    blocks = []
    for s in scripts:
        raw = s.get_attribute("innerHTML")
        if not raw:
            continue
        try:
            blocks.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return blocks
def scrape_top_250(driver: webdriver.Chrome, max_movies: int = 250) -> list:
    """Scrape rank, title, rating and the movie URL for each entry via JSON-LD."""
    print(f"Loading {TOP_250_URL} ...")
    driver.get(TOP_250_URL)
    dismiss_cookie_banner(driver)

    wait = WebDriverWait(driver, 25)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "script[type='application/ld+json']")))
    except Exception:
        driver.save_screenshot("debug_top250_failure.png")
        with open("debug_top250_failure.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        raise RuntimeError(
            "No structured data found on the Top 250 page. Saved debug_top250_failure.png "
            "and debug_top250_failure.html so you can inspect what loaded (likely a CAPTCHA, "
            "consent wall, or IP block)."
        )
    blocks = get_ld_json_blocks(driver)
    item_list = None
    for block in blocks:
        if isinstance(block, dict) and block.get("@type") == "ItemList":
            item_list = block.get("itemListElement", [])
            break

    if not item_list:
        driver.save_screenshot("debug_top250_failure.png")
        with open("debug_top250_failure.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        raise RuntimeError(
            "Found JSON-LD but no ItemList of movies inside it. IMDb may have changed its "
            "structured data format. Saved debug_top250_failure.png / .html for inspection."
        )

    print(f"Found {len(item_list)} movies in the page's structured data.")

    movies = []
    for entry in item_list[:max_movies]:
        try:
            position = entry.get("position")
            item = entry.get("item", {})
            title = item.get("name", "").strip()
            url = item.get("url", "").split("?")[0]
            rating = ""
            agg = item.get("aggregateRating")
            if isinstance(agg, dict):
                rating = str(agg.get("ratingValue", "")).strip()

            movies.append({
                "rank": position,
                "title": title,
                "year": "",   # filled in from the movie's own page below
                "rating": rating,
                "url": url,
                "genre": "",
                "cast": "",
            })
        except Exception as e:
            print(f"  ! Skipped an entry: {e}")
            continue

    return movies


# ---------------------- INDIVIDUAL MOVIE PAGE SCRAPER --------------------- #

def scrape_movie_details(driver: webdriver.Chrome, movie: dict) -> dict:
    """Visit a single movie's page and extract year, genre, and top cast via JSON-LD."""
    try:
        driver.get(movie["url"])
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "script[type='application/ld+json']")))

        blocks = get_ld_json_blocks(driver)
        movie_data = None
        for block in blocks:
            if isinstance(block, dict) and block.get("@type") in ("Movie", "TVSeries", "TVEpisode"):
                movie_data = block
                break

        if movie_data is None:
            print(f"  ! No structured data found for {movie['title']}")
            return movie

        # Genre: can be a string or a list of strings
        genre = movie_data.get("genre", "")
        if isinstance(genre, list):
            movie["genre"] = ", ".join(g.strip() for g in genre if g)
        elif isinstance(genre, str):
            movie["genre"] = genre.strip()

        # Cast: "actor" can be a single dict or a list of dicts, each with a "name"
        actors = movie_data.get("actor", [])
        if isinstance(actors, dict):
            actors = [actors]
        cast_names = [a.get("name", "").strip() for a in actors if isinstance(a, dict) and a.get("name")]
        movie["cast"] = ", ".join(cast_names[:CAST_LIMIT])

        # Year: try datePublished first, fall back to copyrightYear
        date_published = movie_data.get("datePublished", "")
        if date_published:
            movie["year"] = date_published.split("-")[0]
        elif movie_data.get("copyrightYear"):
            movie["year"] = str(movie_data.get("copyrightYear"))

    except Exception as e:
        print(f"  ! Failed to get details for {movie['title']}: {e}")

    return movie


# --------------------------------- MAIN ----------------------------------- #

def main():
    driver = build_driver(headless=HEADLESS)

    try:
        movies = scrape_top_250(driver, max_movies=MAX_MOVIES)

        if SCRAPE_CAST_AND_GENRE:
            print("Visiting individual movie pages for year, genre and cast ...")
            for idx, movie in enumerate(movies, start=1):
                print(f"  [{idx}/{len(movies)}] {movie['title']}")
                scrape_movie_details(driver, movie)
                time.sleep(random.uniform(*REQUEST_DELAY_RANGE))
    finally:
        driver.quit()
    # Save to CSV using pandas
    df = pd.DataFrame(movies, columns=["rank", "title", "year", "rating", "genre", "cast", "url"])
    df.to_csv(OUTPUT_CSV, index=False, quoting=csv.QUOTE_MINIMAL, encoding="utf-8")
    print(f"\nDone! Saved {len(df)} movies to {OUTPUT_CSV}")
if __name__ == "__main__":
    main()
