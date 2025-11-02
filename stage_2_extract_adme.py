import pandas as pd
import asyncio
from playwright.async_api import async_playwright
import os
import re

#--- Configuration ---
INPUT_FILE = "smiles_input.csv"
RESULTS_DIR = "results"
OUTPUT_FILE = os.path.join(RESULTS_DIR, "swissadme_final_output.csv")
MAX_CONCURRENT_BROWSERS = 10  # Politeness limit
#

# --- START: THIS FUNCTION IS NOW CORRECTED ---
# It now looks for a <td> that *starts with* the label text.
# This is more specific and will not accidentally match help text.
async def get_property_text(page, label: str):
    """A robust helper function to extract text from the <td> tag."""
    try:
        # Use a flexible "starts-with" locator
        # This finds a <td> whose text *starts with* the label,
        # (e.g., "Lipinski" or "Log Po/w")
        # and then gets the text of the *next* <td>
        locator = page.locator(f"//td[starts-with(normalize-space(.), '{label}')]/following-sibling::td")
        
        # Use .first to ensure we only get one result
        value = await locator.first.inner_text()
        
        # Specific cleanup for TPSA
        if label == "TPSA":
            value = value.split(" ")[0] # Keep only the number, e.g., "37.30"
        return value.strip()
    except Exception:
        # This is expected if a property doesn't exist for a molecule
        return None
# --- END: FUNCTION CORRECTION ---


async def run_swissadme_and_extract(playwright, compound_name, smiles, semaphore):
    """
    Async worker function.
    Runs one SMILES string through SwissADME, saves the PDF,
    and extracts all requested data points.
    """
    async with semaphore: # Acquire a "slot" from the concurrency limiter
        print(f"  Processing: {compound_name}")
        browser = None
        try:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Added a 90-second timeout to the page load
            await page.goto("https://www.swissadme.ch", timeout=90000)
            
            await page.wait_for_selector("textarea[name='smiles']")
            
            # --- START: HUMAN-LIKE STRATEGY ---
            
            # 1. Click the text area to give it focus
            await page.click("textarea[name='smiles']")
            
            # 2. Type the SMILES string slowly (delay=50ms) to trigger JavaScript
            await page.type("textarea[name='smiles']", f"{smiles} {compound_name}", delay=50)
            
            # 3. Define the SELECTOR for the ENABLED button
            button_selector = "#submitButton:enabled"
            
            # 4. Wait for that selector to appear (i.e., for the button to become enabled)
            await page.wait_for_selector(button_selector, timeout=90000)
            
            # 5. Click the button (which we now know is enabled)
            await page.click(button_selector)
            
            # --- END: HUMAN-LIKE STRATEGY ---
            
            # Wait for the results to load by looking for the "Molecular weight" <td>
            await page.wait_for_selector("td:text-is('Molecular weight')", timeout=90000)
            
            # 1. Save PDF Report (Archival)
            pdf_path = os.path.join(RESULTS_DIR, f"{compound_name}.pdf")
            await page.pdf(path=pdf_path, format="A4")
            
            #--- 2. Extract Specific Data ---
            # --- This list now matches your exact request ---
            data = {
                "Compound": compound_name,
                "SMILES": smiles,
                "Molecular_Formula": await get_property_text(page, "Formula"),
                "Molecular_Weight": await get_property_text(page, "Molecular weight"),
                "MLogP": await get_property_text(page, "Log Po/w (MLOGP)"),
                "TPSA": await get_property_text(page, "TPSA"),
                "H_Bond_Acceptors": await get_property_text(page, "Num. H-bond acceptors"),
                "H_Bond_Donors": await get_property_text(page, "Num. H-bond donors"),
                "Lipinski_Filter": await get_property_text(page, "Lipinski"),
                "Bioavailability_Score": await get_property_text(page, "Bioavailability Score"),
            }
            print(f"  Finished processing: {compound_name}")
            return data
        except Exception as e:
            print(f"  Failed processing {compound_name}: {e}")
            return {"Compound": compound_name, "SMILES": smiles} # Return partial data
        finally:
            if browser:
                await browser.close()

async def main():
    """
    Main async function to read the CSV and orchestrate the parallel tasks.
    """
    # Create results directory if it doesn't exist
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    # Read the input file from Stage 1
    try:
        df_input = pd.read_csv(INPUT_FILE)
    except FileNotFoundError:
        print(f"Error: Input file '{INPUT_FILE}' not found.")
        print("Please run Stage 1 ('stage_1_get_smiles.py') first.")
        sys.exit(1)
        
    # Create a semaphore to limit concurrency
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_BROWSERS)
    
    async with async_playwright() as p:
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
                
        print(f"Starting Stage 2: Processing {len(tasks)} compounds...")
        print(f"Concurrency limit: {MAX_CONCURRENT_BROWSERS} parallel browsers.")
        
        # Run all tasks concurrently
        results_list = await asyncio.gather(*tasks)
        
        # --- THIS IS THE TYPO FIX ---
        # Changed df__final (2 underscores) to df_final (1 underscore)
        df_final = pd.DataFrame([res for res in results_list if res is not None])
        
        # --- This column list now matches your exact request ---
        column_order = [
            "Compound", "SMILES", "Molecular_Formula", "Molecular_Weight", 
            "MLogP", "TPSA", "H_Bond_Acceptors", "H_Bond_Donors", 
            "Lipinski_Filter", "Bioavailability_Score"
        ]
        
        # Reorder columns and save to the final output file
        df_final = df_final.reindex(columns=column_order) 
        df_final.to_csv(OUTPUT_FILE, index=False)
        
        print("-" * 30)
        print(f"Stage 2 Complete.")
        print(f"Final output CSV saved to: {OUTPUT_FILE}")
        print(f"All individual PDF reports saved in: {RESULTS_DIR}/")

if __name__ == "__main__":
    asyncio.run(main())