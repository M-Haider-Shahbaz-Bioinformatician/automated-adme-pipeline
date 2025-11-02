import pubchempy as pcp
import pandas as pd
import sys
import os

# Define input and output file names
INPUT_FILE = "compounds.txt"
OUTPUT_FILE = "smiles_input.csv"

def fetch_smiles_from_pubchem(input_path, output_path):
    """
    Reads a list of compound names from an input text file,
    fetches their canonical SMILES from PubChem, and saves
    them to a CSV file.
    """
    
    # Check if input file exists
    if not os.path.exists(input_path):
        print(f"Error: Input file '{input_path}' not found.")
        print("Please create it with one compound name per line.")
        sys.exit(1)

    # Read compound names from the text file
    with open(input_path, 'r') as f:
        # Read lines and strip whitespace/empty lines
        compound_names = [line.strip() for line in f if line.strip()]

    if not compound_names:
        print(f"Error: Input file '{input_path}' is empty.")
        sys.exit(1)

    print(f"Successfully read {len(compound_names)} compound names.")

    results_list = []  # <--- CORRECTION 1: Initialized as an empty list

    # Iterate through each name and query PubChem
    for name in compound_names:
        smiles_string = None
        try:
            # Query PubChem by name
            results = pcp.get_compounds(name, 'name')
            
            # Handle ambiguity: take the first, most relevant hit
            if results:
                smiles_string = results[0].connectivity_smiles # <--- CORRECTION 2: Added [0] to access first result
                print(f"  Found '{name}': {smiles_string[:30]}...")
            else:
                print(f"  Compound '{name}' not found in PubChem. Skipping.")
        except Exception as e:
            print(f"  An error occurred while fetching '{name}': {e}. Skipping.")

        # Add to our results list, even if SMILES is None (for traceability)
        results_list.append({
            "compound": name,
            "smiles": smiles_string
        })

    # Convert the list of dictionaries to a pandas DataFrame
    df = pd.DataFrame(results_list)

    # Filter out any compounds that were not found
    df_successful = df.dropna(subset=['smiles'])

    # Save the successful results to the output CSV file
    df_successful.to_csv(output_path, index=False)

    print("-" * 30)
    print(f"Stage 1 Complete.")
    print(f"Successfully processed {len(df_successful)} / {len(compound_names)} compounds.")
    print(f"Output saved to '{output_path}'.")

if __name__ == "__main__":
    fetch_smiles_from_pubchem(INPUT_FILE, OUTPUT_FILE)