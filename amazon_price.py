import time
import csv
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
import yagmail

# ----------- CONFIGURE -----------
SENDER_EMAIL = os.getenv("EMAIL_USERNAME")
APP_PASSWORD = os.getenv("EMAIL_PASSWORD")
RECIPIENTS = [email.strip() for email in os.getenv("EMAIL_RECIPIENTS", "").split(',')]
SUBJECT_LINE = 'Amazon Daily Price Tracker Report'

product_urls = [
    'https://www.amazon.com/dp/B00O5NEQP8',
    'https://www.amazon.com/CRZ-YOGA-All-Day-Comfort-Pants/dp/B09YXL4Y2H',
    'https://www.amazon.com/CRZ-YOGA-All-Day-Comfort-Shorts/dp/B0B82HPRMT'
]

csv_file = 'amazon_price_tracking.csv'
today = datetime.now().strftime('%Y-%m-%d')
yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

# Track existing entries
existing_entries = set()
price_history = {}

if os.path.exists(csv_file):
    with open(csv_file, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row['URL']
            if key not in price_history:
                price_history[key] = []
            price_history[key].append({
                'date': row['Date'],
                'price': row['Price (USD)'],
                'name': row['Product Name'],
            })
            existing_entries.add((row['Date'], row['URL']))

# Setup browser
options = uc.ChromeOptions()
options.headless = True
driver = uc.Chrome(options=options)

# Results for email
daily_report = []

# Load and clean existing rows
existing_rows = []
if os.path.exists(csv_file):
    with open(csv_file, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        for row in reader:
            # Remove same-day rows with N/A price for this product
            if row['Date'] == today and row['URL'] in product_urls and row['Price (USD)'] == 'N/A':
                continue
            existing_rows.append(row)

# Now write cleaned data back
with open(csv_file, mode='w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['Date', 'Product Name', 'Price (USD)', 'URL'])
    writer.writeheader()
    writer.writerows(existing_rows)

    # Refresh today's existing entries (for logic below)
    existing_entries = set((row['Date'], row['URL']) for row in existing_rows)
    price_history = {}
    for row in existing_rows:
        key = row['URL']
        if key not in price_history:
            price_history[key] = []
        price_history[key].append({
            'date': row['Date'],
            'price': row['Price (USD)'],
            'name': row['Product Name'],
        })

    for url in product_urls:
        # Skip only if valid price for today already exists
        already_recorded = False
        for entry in price_history.get(url, []):
            if entry['date'] == today and entry['price'] != 'N/A':
                already_recorded = True
                break
        if already_recorded:
            print(f"Already recorded valid price today: {url}")
            continue

        try:
            print(f"\nScraping: {url}")
            driver.get(url)
            time.sleep(5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            title_tag = soup.select_one('#productTitle')
            product_name = title_tag.get_text(strip=True) if title_tag else 'N/A'

            price_tag = soup.select_one('.a-price .a-offscreen')
            price_text = price_tag.get_text(strip=True).replace('$', '') if price_tag else 'N/A'

            print(f"→ {product_name[:60]}... | ${price_text}")
            writer.writerow({
                'Date': today,
                'Product Name': product_name,
                'Price (USD)': price_text,
                'URL': url
            })

            # Historical data
            previous_price = 'N/A'
            lowest_price = price_text
            all_prices = []
            lowest_price_date = today

            for entry in price_history.get(url, []):
                try:
                    p = float(entry['price'])
                    all_prices.append(p)
                    if entry['date'] == yesterday:
                        previous_price = f"{p:.2f}"
                    if p < float(lowest_price):
                        lowest_price = f"{p:.2f}"
                        lowest_price_date = entry['date']
                except ValueError:
                    continue

            try:
                current_price_float = float(price_text)
                if all_prices:
                    lowest_price = f"{min(all_prices + [current_price_float]):.2f}"
                else:
                    lowest_price = f"{current_price_float:.2f}"
            except ValueError:
                lowest_price = 'N/A'

            daily_report.append({
                'name': product_name,
                'url': url,
                'today_price': price_text,
                'yesterday_price': previous_price,
                'lowest_price': lowest_price,
                'lowest_price_date': lowest_price_date
            })

        except Exception as e:
            print(f"Error scraping {url}: {e}")
            writer.writerow({
                'Date': today,
                'Product Name': 'ERROR',
                'Price (USD)': 'N/A',
                'URL': url
            })
            daily_report.append({
                'name': 'ERROR',
                'url': url,
                'today_price': 'N/A',
                'yesterday_price': 'N/A',
                'lowest_price': 'N/A',
                'lowest_price_date': today
            })


driver.quit()

# ---------------- EMAIL & TEXT REPORT ----------------
if daily_report:
    yag = yagmail.SMTP(SENDER_EMAIL, APP_PASSWORD)

    # Build email report
    body_lines = [f"Date: {today}", "", "Amazon Price Tracker Summary:\n"]
    sms_lines = []

    for entry in daily_report:
        body_lines.append(f"{entry['name']}")
        body_lines.append(f"{entry['url']}")
        body_lines.append(f"Today: ${entry['today_price']}")
        body_lines.append(f"Yesterday: ${entry['yesterday_price']}")
        body_lines.append(f"All-Time Low: ${entry['lowest_price']} on {entry['lowest_price_date']}\n")

    # Send email report
    yag.send(
        to=RECIPIENTS,
        subject=SUBJECT_LINE,
        contents="\n".join(body_lines)
    )
    print(f"\nEmail report sent to {RECIPIENTS}")
else:
    print("No new entries to email today.")

