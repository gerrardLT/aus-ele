import argparse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from tqdm import tqdm

from aemo_wem_scraper import scrape_wem_date
from database import DatabaseManager

# Suppress detailed logs to make room for tqdm
logging.getLogger("aemo_wem_scraper").setLevel(logging.WARNING)

def worker(date_obj, db_path):
    import time
    db = DatabaseManager(db_path)
    count = scrape_wem_date(date_obj, db)
    return date_obj, count

def run_concurrent_scraping(start_date: str, end_date: str, db_path: str, max_workers: int = 2):
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    dates_to_scrape = []
    curr_dt = start_dt
    while curr_dt <= end_dt:
        dates_to_scrape.append(curr_dt)
        curr_dt += timedelta(days=1)
        
    print(f"\n[🚀 WEM Data Init] Start fetching {len(dates_to_scrape)} days ({start_date} to {end_date}) using {max_workers} threads.")
    total_records = 0
    start_time = datetime.now()
    
    with tqdm(total=len(dates_to_scrape), desc="WEM Syncing", unit="day") as pbar:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(worker, dt, db_path): dt for dt in dates_to_scrape}
            
            for future in as_completed(futures):
                dt = futures[future]
                try:
                    dt_res, count = future.result()
                    if count > 0:
                        total_records += count
                    # Update progress bar
                    pbar.update(1)
                    pbar.set_postfix({"Latest Date": dt_res.strftime('%Y-%m-%d'), "Total Inserted": total_records})
                except Exception as e:
                    print(f"\n[!] Error on {dt.strftime('%Y-%m-%d')}: {e}")
                    pbar.update(1)
                
    elapsed = datetime.now() - start_time
    print(f"\n✅ All Done! Inserted {total_records} records in {elapsed}.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=str, default="2020-01-01")
    parser.add_argument("--end", type=str, default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument("--db", type=str, default="aemo_data.db")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    
    run_concurrent_scraping(args.start, args.end, args.db, args.workers)
