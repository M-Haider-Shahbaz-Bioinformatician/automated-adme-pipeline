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
USER_AGENT_STRING = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
# ---------------------

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
            context = await browser.new_context(user_agent=USER_AGENT_STRING)
            page = await context.new_page()
            
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
            return data # Return partial data (at least Compound and SMILES)
            
        finally:
            # Close everything, catching individual errors
            try:
                if page:
                    await page.close()
            except Exception:
                pass # Ignore errors during cleanup
            try:
                if context:
                    await context.close()
            except Exception:
                pass # Ignore errors during cleanup
            try:
                if browser:
                    await browser.close()
            except Exception:
                pass # Ignore errors during cleanup
            

async def main():
    """
    Main async function to find all batch files and process them one by one.
    Implements compound-level resume logic.
    """
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    # Find all batch files
    batch_files = sorted(glob.glob("smiles_input_batch_*.csv"))
    
    if not batch_files:
        print("Error: No 'smiles_input_batch_*.csv' files found.")
        print("Please run 'stage_1_get_smiles_v0.2.py' first.")
        sys.exit(1)
        
    print(f"Found {len(batch_files)} batch file(s) to process.")
    
    async with async_playwright() as p:
        
        for i, batch_file in enumerate(batch_files):
            print("-" * 30)
            print(f"Checking Batch {i+1} / {len(batch_files)}: {batch_file}")
            
            batch_num = i + 1
            intermediate_result_file = os.path.join(RESULTS_DIR, f"results_batch_{batch_num}.csv")
            
            # --- START: NEW "RESUME" FEATURE (COMPOUND-LEVEL) ---
            already_processed_compounds = set()
            all_batch_results = []
            
            if os.path.exists(intermediate_result_file):
                try:
                    print(f"  > Found existing results file: {intermediate_result_file}.")
                    df_existing = pd.read_csv(intermediate_result_file)
                    if 'Compound' in df_existing.columns and not df_existing.empty:
                        already_processed_compounds = set(df_existing['Compound'])
                        all_batch_results = df_existing.to_dict('records') # Load existing data
                        print(f"  > Loaded {len(already_processed_compounds)} already processed compounds.")
                    else:
                        print(f"  > Results file is empty or has no 'Compound' column. Will process all.")
                except pd.errors.EmptyDataError:
                    print(f"  > Existing results file {intermediate_result_file} is empty. Will process all.")
                except Exception as e:
                    print(f"  > Error loading {intermediate_result_file}: {e}. Will re-process all for this batch.")
            # --- END: NEW "RESUME" FEATURE ---

            print(f"Processing Batch {batch_num} / {len(batch_files)}: {batch_file}")
            
            try:
                df_input = pd.read_csv(batch_file)
                if 'compound' not in df_input.columns or 'smiles' not in df_input.columns:
                     print(f"  Error: {batch_file} is missing 'compound' or 'smiles' column. Skipping.")
                     continue
            except Exception as e:
                print(f"  Error reading {batch_file}: {e}. Skipping.")
                continue
                
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_BROWSERS)
            tasks = []
            compounds_to_process_count = 0
            
            for _, row in df_input.iterrows():
                # Check if compound is already processed
                if row['compound'] in already_processed_compounds:
                    # print(f"    Skipping already processed: {row['compound']}") # Optional: too much logging
                    continue
                    
                if pd.notna(row['smiles']):
                    tasks.append(
                        run_swissadme_and_extract(
                            p,
                            row['compound'],
                            row['smiles'],
                            semaphore
                        )
                    )
                    compounds_to_process_count += 1
            
            if compounds_to_process_count == 0:
                print(f"  > All {len(df_input)} compounds in this batch are already processed. Skipping to next batch.")
                continue
            
            print(f"  > Processing {compounds_to_process_count} new compound(s) in this batch...")
            
            # Run all tasks for this batch
            new_results = await asyncio.gather(*tasks)
            
            # Add new results to the (potentially) existing results
            all_batch_results.extend([res for res in new_results if res is not None and 'Compound' in res])
            
            # Save the intermediate results for this batch
            if not all_batch_results:
                print(f"  > No valid results for Batch {batch_num}. Saving empty file.")
                # Define columns even for an empty DF to avoid issues later
                df_batch_final = pd.DataFrame(columns=["Compound", "SMILES"]) 
            else:
                df_batch_final = pd.DataFrame(all_batch_results)

            df_batch_final.to_csv(intermediate_result_file, index=False)
            print(f"  > Finished Batch {batch_num}. Results saved/updated in {intermediate_result_file}")
            
            # If it's not the last batch, add the cooldown
            if i < len(batch_files) - 1:
                print(f"--- Cooling down for {BATCH_COOLDOWN_SECONDS} seconds... ---")
                await asyncio.sleep(BATCH_COOLDOWN_SECONDS)
        
    print("=" * 30)
    print("All batches processed. Combining results...")
    
    # Combine all intermediate results at the end
    all_batch_results_files = sorted(glob.glob(os.path.join(RESULTS_DIR, "results_batch_*.csv")))
    
    if not all_batch_results_files:
        print("No batch result files were found. Final output file will be empty.")
        # Use return instead of sys.exit in async function
        return

    df_list = []
    for f in all_batch_results_files:
        try:
            df_temp = pd.read_csv(f)
            if not df_temp.empty:
                df_list.append(df_temp)
            else:
                 print(f"  > Warning: {f} is empty. Skipping.")
        except pd.errors.EmptyDataError:
            print(f"  > Warning: {f} is empty. Skipping.")

    if not df_list:
        print("All result files were empty. No final file created.")
        return

    df_final = pd.concat(df_list)
    
    column_order = [
        "Compound", "SMILES", "Molecular_Formula", "Molecular_Weight", 
        "MLogP", "TPSA", "H_Bond_Acceptors", "H_Bond_Donors", 
        "Lipinski_Filter", "Bioavailability_Score"
    ]
    
    # Reindex, filling missing columns with None (or NaN)
    df_final = df_final.reindex(columns=column_order) 
    df_final.to_csv(FINAL_OUTPUT_FILE, index=False)
    
    print(f"Stage 2 Complete.")
    print(f"Final combined output CSV saved to: {FINAL_OUTPUT_FILE}")
    
    # --- START: NEW "CLEANUP" FEATURE ---
    print("Cleaning up temporary batch files...")
    for f in all_batch_results_files:
        try:
            os.remove(f)
            print(f"  > Removed {f}")
        except Exception as e:
            print(f"  > Error removing {f}: {e}")
    # --- END: NEW "CLEANUP" FEATURE ---
    
    print("Cleanup complete.")
    print(f"All individual PDF reports saved in: {RESULTS_DIR}/")

if __name__ == "__main__":  
    asyncio.run(main())