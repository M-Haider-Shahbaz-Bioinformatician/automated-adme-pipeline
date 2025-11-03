# **Automated ADME-Tox Profiling Pipeline**

This is a two-stage computational pipeline to automate the process of Absorption, Distribution, Metabolism, and Excretion (ADME) profiling for a list of chemical compounds.

The workflow fetches compound data from PubChem and then extracts detailed pharmacokinetic and physicochemical properties from the SwissADME web service.

This script is designed to be robust against server-side bot detection by batching requests, simulating a human User-Agent, and running compounds one at a time with built-in "cooldown" periods.

## **Project Stages**

### **Stage 1: Name-to-SMILES & Batching (stage\_1\_get\_smiles\_v0.2.py)**

* **Input:** compounds.txt (a plain text file with one compound name per line).  
* **Process:** Queries the PubChem PUG REST API to find the canonical SMILES string for each compound. It then splits the full list into multiple small batch files (e.g., smiles\_input\_batch\_1.csv).  
* **Output:** Multiple smiles\_input\_batch\_\*.csv files.

### **Stage 2: Batch Processing (stage\_2\_ectract\_adme\_v0.2.py)**

* **Input:** All smiles\_input\_batch\_\*.csv files from Stage 1\.  
* **Process:** Uses browser automation (Playwright) to run each compound, one by one. It processes one full batch file, pauses for a 60-second "cooldown," and then moves to the next batch.  
* **Output:**  
  * results/swissadme\_final\_output.csv: A **single, combined** CSV file containing all extracted properties from all batches.  
  * results/: A directory containing individual PDF reports for each compound.

## **Technology Stack**

* Python 3.10+  
* PubChemPy: For interacting with the PubChem API.  
* Pandas: For reading/writing CSV files and managing data.  
* Playwright & Asyncio: For robust, asynchronous browser automation.

## **Setup and Installation**

1. **Clone the repository:**  
   git clone \[https://github.com/M-Haider-Shahbaz-Bioinformatician/automated-adme-pipeline.git\](https://github.com/M-Haider-Shahbaz-Bioinformatician/automated-adme-pipeline.git)  
   cd automated-adme-pipeline

2. **Create and activate a virtual environment:**  
   \# On Windows  
   python \-m venv venv  
   .\\venv\\Scripts\\activate

   \# On macOS/Linux  
   python3 \-m venv venv  
   source venv/bin/activate

3. **Install the required libraries:**  
   pip install \-r requirements.txt

4. **Install Playwright's browser binaries** (one-time setup):  
   playwright install

## **How to Run the Pipeline**

### **Step 1: Create your input file**

Edit the compounds.txt file and add your full list of compound names (e.g., 123+ names).

### **Step 2: Run Stage 1 (Batch Creator)**

python stage\_1\_get\_smiles\_v0.2.py

This will fetch all SMILES and create the small smiles\_input\_batch\_\*.csv files.

### **Step 3: Run Stage 2 (Batch Runner)**

python stage\_2\_ectract\_adme\_v0.2.py

This will slowly and reliably process all batch files and create the final swissadme\_final\_output.csv file. This may take a long time to complete.

## **MAINTENANCE WARNING**

This pipeline relies on web scraping. If the SwissADME website changes its HTML, the script will break. You will need to inspect the website manually and update the selectors (e.g., td:text-is('Molecular weight')) in stage\_2\_ectract\_adme\_v0.2.py to match.