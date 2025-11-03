import pandas as pd
import asyncio
from playwright.async_api import async_playwright
import os
import re
import sys
import glob # Used to find all the batch files

#--- Configuration ---
RESULTS_DIR = "results"
FINAL_OUTPUT_FILE = os.path.join(RESULTS_DIR, "swissadme_final_output.csv")
MAX_CONCURRENT_BROWSERS = 1  # Keep this at 1 for reliability
BATCH_COOLDOWN_SECONDS = 60  # 60-second pause between batches
# --- START: NEW FIX ---
# This makes us look like a real browser, not a bot.
USER_AGENT_STRING = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
# --- END: NEW FIX ---

async def get_property_text(page, label: str):
    """A robust helper function to extract text from the <td> tag."""
    try:
        locator = page.locator(f"//td[starts-with(normalize-space(.), '{label}')]/following-sibling::td")
        value = await locator.first.inner_text(timeout=5000)
        if label == "TPSA":
            value = value.split(" ")[0]
        return value.strip()
    except Exception:
        return None

async def run_swissadme_and_extract(playwright, compound_name, smiles, semaphore):
    """Async worker function to process one compound."""
    async with semaphore:
        print(f"    Processing compound: {compound_name}")
        browser = None
        context = None
        page = None
        data = {"Compound": compound_name, "SMILES": smiles}
        
        try:
            # Add a 3-second "human" pause *before* each request
            await asyncio.sleep(3)
        
            browser = await playwright.chromium.launch(headless=True)
            
            # --- START: NEW FIX ---
            # Create a new browser "context" with our fake User-Agent
            context = await browser.new_context(user_agent=USER_AGENT_STRING)
            page = await context.new_page()
            # --- END: NEW FIX ---
            
            await page.goto("https://www.swissadme.ch", timeout=90000)
            
            try:
                accept_button = page.locator('button:has-text("Accept"), button:has-text("Agree")')
                await accept_button.first.click(timeout=3000)
            except Exception:
                pass 
            
            await page.wait_for_selector("textarea[name='smiles']", timeout=90000)
            
            await page.click("textarea[name='smiles']")
            await page.type("textarea[name='smiles']", f"{smiles} {compound_name}", delay=50)
            
            button_selector = "#submitButton:enabled"
            await page.wait_for_selector(button_selector, timeout=90000)
            await page.click(button_selector)
            
            await page.wait_for_selector("td:text-is('Molecular weight')", timeout=90000)
            
            pdf_path = os.path.join(RESULTS_DIR, f"{compound_name}.pdf")
            await page.pdf(path=pdf_path, format="A4")
            
            data.update({
                "Molecular_Formula": await get_property_text(page, "Formula"),
                "Molecular_Weight": await get_property_text(page, "Molecular weight"),
                "MLogP": await get_property_text(page, "Log Po/w (MLOGP)"),
                "TPSA": await get_property_text(page, "TPSA"),
                "H_Bond_Acceptors": await get_property_text(page, "Num. H-bond acceptors"),
                "H_Bond_Donors": await get_property_text(page, "Num. H-bond donors"),
                "Lipinski_Filter": await get_property_text(page, "Lipinski"),
                "Bioavailability_Score": await get_property_text(page, "Bioavailability Score"),
            })
            print(f"    Finished processing: {compound_name}")
            return data
        
        except Exception as e:
            print(f"    Failed processing {compound_name}: {e}")
            return data
            
        finally:
            # Close everything in order
            if page:
                await page.close()
            if context:
                await context.close()
            if browser:
                await browser.close()
            

async def main():
    """
    Main async function to find all batch files and process them one by one.
    """
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    # Find all batch files
    batch_files = sorted(glob.glob("smiles_input_batch_*.csv"))
    
    if not batch_files:
        print("Error: No 'smiles_input_batch_*.csv' files found.")
        print("Please run 'stage_1_make_batches.py' first.")
        sys.exit(1)
        
    print(f"Found {len(batch_files)} batch file(s) to process.")
    
    all_results_list = []
    
    async with async_playwright() as p:
        
        for i, batch_file in enumerate(batch_files):
            print("-" * 30)
            print(f"Processing Batch {i+1} / {len(batch_files)}: {batch_file}")
            
            try:
                df_input = pd.read_csv(batch_file)
            except Exception as e:
                print(f"  Error reading {batch_file}: {e}. Skipping.")
                continue
                
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_BROWSERS)
            tasks = []
            
            for _, row in df_input.iterrows():
                if pd.notna(row['smiles']):
                    tasks.append(
                        run_swissadme_and_extract(
                            p,
                            row['compound'],
                            row['smiles'],
                            semaphore
                        )
                    )
            
            # Run all tasks for this batch
            batch_results = await asyncio.gather(*tasks)
            all_results_list.extend(batch_results)
            
            print(f"Finished Batch {i+1} / {len(batch_files)}.")
            
            # If it's not the last batch, add the cooldown
            if i < len(batch_files) - 1:
                print(f"--- Cooling down for {BATCH_COOLDOWN_SECONDS} seconds... ---")
                await asyncio.sleep(BATCH_COOLDOWN_SECONDS)
        
    print("=" * 30)
    print("All batches processed.")
    
    # Convert all results into the final DataFrame
    df_final = pd.DataFrame([res for res in all_results_list if res is not None])
    
    column_order = [
        "Compound", "SMILES", "Molecular_Formula", "Molecular_Weight", 
        "MLogP", "TPSA", "H_Bond_Acceptors", "H_Bond_Donors", 
        "Lipinski_Filter", "Bioavailability_Score"
    ]
    
    df_final = df_final.reindex(columns=column_order) 
    df_final.to_csv(FINAL_OUTPUT_FILE, index=False)
    
    print(f"Stage 2 Complete.")
    print(f"Final combined output CSV saved to: {FINAL_OUTPUT_FILE}")
    print(f"All individual PDF reports saved in: {RESULTS_DIR}/")

if __name__ == "__main__":
    asyncio.run(main())