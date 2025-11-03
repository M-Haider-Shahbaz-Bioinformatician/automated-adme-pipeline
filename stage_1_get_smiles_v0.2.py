import pubchempy as pcp
import pandas as pd
import sys
import os

# --- Configuration ---
INPUT_FILE = "compounds.txt"
BATCH_SIZE = 15  # As you suggested, 15 compounds per file
# ---------------------

def fetch_and_batch_smiles(input_path, batch_size):
    """
    Reads compound names, fetches SMILES from PubChem,
    and saves them into multiple small batch files.
    """
    
    # Check if input file exists
    if not os.path.exists(input_path):
        print(f"Error: Input file '{input_path}' not found.")
        print("Please create it with one compound name per line.")
        sys.exit(1)

    # Read compound names from the text file
    with open(input_path, 'r') as f:
        compound_names = [line.strip() for line in f if line.strip()]

    if not compound_names:
        print(f"Error: Input file '{input_path}' is empty.")
        sys.exit(1)

    print(f"Successfully read {len(compound_names)} compound names.")
    print("Fetching all SMILES from PubChem (this may take a moment)...")

    results_list = []
    # Iterate through each name and query PubChem
    for name in compound_names:
        smiles_string = None
        try:
            results = pcp.get_compounds(name, 'name')
            if results:
                smiles_string = results[0].connectivity_smiles
                print(f"  Found '{name}': {smiles_string[:30]}...")
            else:
                print(f"  Compound '{name}' not found in PubChem. Skipping.")
        except Exception as e:
            print(f"  An error occurred while fetching '{name}': {e}. Skipping.")

        results_list.append({
            "compound": name,
            "smiles": smiles_string
        })

    # Convert the list of dictionaries to a pandas DataFrame
    df = pd.DataFrame(results_list)
    df_successful = df.dropna(subset=['smiles'])
    
    print("-" * 30)
    print(f"Successfully fetched {len(df_successful)} SMILES strings.")
    
    # Calculate the number of batches needed (ceiling division)
    num_batches = (len(df_successful) + batch_size - 1) // batch_size
    print(f"Splitting into {num_batches} batch file(s) of {batch_size} compounds each.")

    # Loop and create each batch file
    for i in range(num_batches):
        start_index = i * batch_size
        end_index = (i + 1) * batch_size
        
        df_batch = df_successful.iloc[start_index:end_index]
        
        output_filename = f"smiles_input_batch_{i+1}.csv"
        df_batch.to_csv(output_filename, index=False)
        print(f"  Created batch file: {output_filename} ({len(df_batch)} compounds)")

    print("-" * 30)
    print("Stage 1 (Batching) Complete.")

if __name__ == "__main__":
    fetch_and_batch_smiles(INPUT_FILE, BATCH_SIZE)