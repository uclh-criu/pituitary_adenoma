# utils/common_utils.py
import re
import os
import ast  # For safely evaluating Python literals
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import ConfusionMatrixDisplay
import json
# Add tqdm for progress bars
from tqdm import tqdm
# Add pandas for CSV processing
import pandas as pd
# Add dotenv for OpenAI API keys
from dotenv import load_dotenv

# Get the appropriate data path based on the config
def get_data_path(config):
    """
    Determine the correct dataset path based on the DATA_SOURCE value in config.
    
    Args:
        config: The configuration object containing data source settings.
        
    Returns:
        str: Path to the dataset file to be used.
    """
    if not hasattr(config, 'DATA_SOURCE'):
        # Default to synthetic data if DATA_SOURCE is not defined
        return getattr(config, 'SYNTHETIC_DATASET_PATH', 'data/synthetic_data.json')
    
    data_source = config.DATA_SOURCE.lower()
    
    if data_source == 'synthetic':
        return getattr(config, 'SYNTHETIC_DATASET_PATH', 'data/synthetic_data.json')
    elif data_source == 'imaging':
        return getattr(config, 'IMAGING_DATA_PATH', 'data/epic_imaging_reports.csv')
    elif data_source == 'notes':
        return getattr(config, 'NOTES_DATA_PATH', 'data/epic_notes.csv')
    elif data_source == 'letters':
        return getattr(config, 'LETTERS_DATA_PATH', 'data/epic_letters.csv')
    elif data_source == 'sample':
        return getattr(config, 'SAMPLE_DATA_PATH', 'data/sample.csv')
    else:
        # Default to synthetic data if DATA_SOURCE is not recognized
        print(f"WARNING: Unrecognized DATA_SOURCE '{data_source}'. Using synthetic data.")
        return getattr(config, 'SYNTHETIC_DATASET_PATH', 'data/synthetic_data.json')

# Parse date string (Moved from data_preparation)
def parse_date_string(date_str):
    """
    Parse a date string in various formats and return a standard YYYY-MM-DD format.
    Returns None if parsing fails.
    """
    date_str = date_str.strip()
    
    try:
        # Try common formats using datetime.strptime
        formats = [
            # DD-MM-YYYY, DD/MM/YYYY, DD.MM.YYYY
            '%d-%m-%Y', '%d/%m/%Y', '%d.%m.%Y',
            # DD-MM-YY, DD/MM/YY, DD.MM.YY
            '%d-%m-%y', '%d/%m/%y', '%d.%m.%y',
            # YYYY-MM-DD
            '%Y-%m-%d',
            # Month names
            '%d %b %Y', '%d %B %Y',
            '%d %b\'%y', '%dst %b %Y', '%dnd %b %Y', '%drd %b %Y', '%dth %b %Y'
        ]
        
        for fmt in formats:
            try:
                date_obj = datetime.strptime(date_str, fmt)
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                continue
                
        # If still not parsed, try more complex regex patterns
        # 1. Match patterns like "3rd Feb'23" or "3rd February 2023"
        match = re.search(r'(\d+)(?:st|nd|rd|th)?\s+([a-zA-Z]+)[\']*\s*[\']*(\d{2,4})', date_str)
        if match:
            day, month_str, year = match.groups()
            
            month_names = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }
            month = month_names.get(month_str.lower()[:3])
            if month:
                if len(year) == 2: year = '20' + year
                date_obj = datetime(int(year), month, int(day))
                return date_obj.strftime('%Y-%m-%d')
        
        # 2. Try to match date with time like "02/02/2023 @1445"
        match = re.search(r'(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\s*[@at]*\s*\d+', date_str)
        if match:
            # Recursive call to handle the extracted date part
            return parse_date_string(match.group(1))
            
        return None
    except Exception:
        return None

# Extract diagnoses and dates with their positions from text
def extract_entities(text):
    """
    Extract underscore-formatted diagnoses and parenthesized dates with their positions.
    Parses dates into YYYY-MM-DD format.
    Returns diagnoses as [(diag_str, pos)] and dates as [(parsed_date_str, raw_date_str, pos)].
    """
    # Handle None, nan, or empty string input
    if text is None or pd.isna(text):
        return [], []
    if isinstance(text, str) and (text.strip() == '' or text.lower() == 'nan'):
        return [], []

    diagnoses = []
    # Regex captures one or more word characters (alphanumeric + underscore)
    # followed by [dx], [diagnosis], or [diagno sis]
    for match in re.finditer(r'(\w+)\[(?:dx|diagnosis|diagno\s*sis)\]', text):
        diagnosis = match.group(1).lower() # Capture group 1 (the diagnosis), ensure lowercase
        position = match.start(1) # Start position of the captured diagnosis word
        diagnoses.append((diagnosis, position))

    dates = []
    # Regex to capture content within parentheses followed by [date]
    for match in re.finditer(r'\(([^)]+)\)\[date\]', text):
        raw_date_str = match.group(1).strip()
        position = match.start(1) # Position of the content inside parentheses
        
        # Parse the date string here
        parsed_date = parse_date_string(raw_date_str)
        
        # Only add if parsing was successful
        if parsed_date:
            dates.append((parsed_date, raw_date_str, position))
    
    # Print diagnostic info only if text is valid and entities weren't found
    if isinstance(text, str) and text.strip() and text.lower() != 'nan':
        if not diagnoses:
            print("Warning: No diagnoses found in the text. Check the text format.")
            print(f"Text sample (first 100 chars): {text[:100]}...")
        
        if not dates:
            print("Warning: No dates found in the text. Check the text format.")
            print(f"Text sample (first 100 chars): {text[:100]}...")

    return diagnoses, dates

# Helper function to load dataset, select samples, prepare gold standard, and extract entities
def load_and_prepare_data(dataset_path, num_samples, config=None):
    """
    Loads dataset, selects samples, prepares gold standard, and pre-extracts entities.
    Supports both synthetic data from JSON and real data from CSV.
    
    Args:
        dataset_path (str): Path to the dataset file (JSON or CSV).
        num_samples (int): Maximum number of samples to use (if provided).
        config: Configuration object to determine the data source.

    Returns:
        tuple: (prepared_test_data, gold_standard) or (None, None) if loading fails.
               prepared_test_data is a list of dicts {'text': ..., 'entities': ...}.
               gold_standard is a list of dicts {'note_id': ..., 'diagnosis': ..., 'date': ...}.
    """
    # If config is provided, use it to get the correct dataset path
    if config:
        dataset_path = get_data_path(config)
    
    # Determine if we're using real data
    using_real_data = False
    if config and hasattr(config, 'DATA_SOURCE'):
        using_real_data = config.DATA_SOURCE.lower() != 'synthetic'
    
    if using_real_data:
        return load_real_data(config, num_samples)
    else:
        return load_synthetic_data(dataset_path, num_samples)

def load_synthetic_data(dataset_path, num_samples):
    """
    Loads synthetic data from a JSON file.
    """
    if not os.path.exists(dataset_path):
        print(f"Error: Dataset not found at {dataset_path}")
        return None, None

    print(f"Loading synthetic dataset from {dataset_path}...")
    try:
        with open(dataset_path, 'r') as f:
            full_dataset = json.load(f)
    except Exception as e:
        print(f"Error loading dataset: {e}")
        return None, None

    # Calculate the 80/20 split point
    split_point = int(len(full_dataset) * 0.8)
    
    # Use the last 20% of the dataset for evaluation
    dataset = full_dataset[split_point:]
    print(f"Using last {len(dataset)}/{len(full_dataset)} samples (20%) for evaluation.")
    
    # If a specific number of samples is requested, limit to that
    if num_samples and num_samples < len(dataset):
        test_data = dataset[:num_samples]
        print(f"Limiting to {num_samples} evaluation samples.")
    else:
        test_data = dataset
        print(f"Using all {len(test_data)} evaluation samples.")

    # Prepare gold standard list with progress bar
    gold_standard = []
    with tqdm(total=len(test_data), desc="Preparing gold standard", unit="note") as pbar:
        for i, entry in enumerate(test_data):
            # Check if 'ground_truth' exists and is iterable
            if 'ground_truth' in entry and isinstance(entry['ground_truth'], list):
                 for section in entry['ground_truth']:
                    # Check if 'date' and 'diagnoses' exist
                    if 'date' in section and 'diagnoses' in section and isinstance(section['diagnoses'], list):
                        for diag in section['diagnoses']:
                            # Check if 'diagnosis' exists
                            if 'diagnosis' in diag:
                                 gold_standard.append({
                                    'note_id': i,
                                    'diagnosis': str(diag['diagnosis']).lower(), # Ensure string and lower
                                    'date': section['date'] # Assume date is already YYYY-MM-DD
                                })
                            else:
                                 print(f"Warning: Missing 'diagnosis' key in note {i}, section date {section.get('date', 'N/A')}")
                    else:
                         print(f"Warning: Missing 'date' or 'diagnoses' key, or 'diagnoses' not a list in note {i}, section date {section.get('date', 'N/A')}")
            else:
                 print(f"Warning: Missing or invalid 'ground_truth' in note {i}")
            
            # Update progress bar
            pbar.update(1)

    print(f"Prepared gold standard with {len(gold_standard)} relationships.")

    # Pre-extract entities for efficiency with progress bar
    print("Pre-extracting entities...")
    prepared_test_data = []
    with tqdm(total=len(test_data), desc="Pre-extracting entities", unit="note") as pbar:
        for entry in test_data:
            text = entry.get('clinical_note', '') # Handle missing 'clinical_note'
            entities = extract_entities(text)
            prepared_test_data.append({
                'note': text,
                'entities': entities
            })
            # Update progress bar
            pbar.update(1)

    return prepared_test_data, gold_standard

def load_real_data(config, num_samples):
    """
    Loads real data from a CSV file.
    
    Args:
        config: The configuration object containing paths and column names.
        num_samples (int): Maximum number of samples to use (if provided).
        
    Returns:
        tuple: (prepared_test_data, gold_standard) or (None, None) if loading fails.
    """
    dataset_path = get_data_path(config)
    text_column = config.REAL_DATA_TEXT_COLUMN
    gold_column = getattr(config, 'REAL_DATA_GOLD_COLUMN', None)
    
    # Get column names for annotations if they exist in config
    diagnoses_column = getattr(config, 'REAL_DATA_DIAGNOSES_COLUMN', None)
    dates_column = getattr(config, 'REAL_DATA_DATES_COLUMN', None)
    timestamp_column = getattr(config, 'REAL_DATA_TIMESTAMP_COLUMN', None)
    
    if not os.path.exists(dataset_path):
        print(f"Error: Real dataset not found at {dataset_path}")
        return None, None
    
    print(f"Loading real dataset from {dataset_path}...")
    try:
        # Read the CSV file
        df = pd.read_csv(dataset_path)
        
        # Check if the text column exists
        if text_column not in df.columns:
            print(f"Error: Text column '{text_column}' not found in CSV. Available columns: {list(df.columns)}")
            return None, None
            
        print(f"Found {len(df)} records in CSV.")
        
        # If a specific number of samples is requested, limit to that
        if num_samples and num_samples < len(df):
            df = df.iloc[:num_samples]
            print(f"Limiting to {num_samples} samples.")
        
        # Check if timestamp column exists (for relative date extraction)
        relative_date_extraction_enabled = False
        if hasattr(config, 'ENABLE_RELATIVE_DATE_EXTRACTION') and config.ENABLE_RELATIVE_DATE_EXTRACTION:
            if timestamp_column and timestamp_column in df.columns:
                relative_date_extraction_enabled = True
                print(f"Relative date extraction enabled using timestamp column: {timestamp_column}")
                
                # Add new column for storing LLM extracted dates
                df['llm_extracted_dates'] = None
            else:
                print(f"Warning: Relative date extraction enabled in config but timestamp column '{timestamp_column}' not found in CSV")
            
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return None, None
    
    # Prepare gold standard list if gold_column exists
    gold_standard = []
    
    if gold_column and gold_column in df.columns:
        print("Found gold standard column. Processing gold standard data...")
        
        with tqdm(total=len(df), desc="Preparing gold standard", unit="note") as pbar:
            for i, row in df.iterrows():
                # Check if the gold standard cell is not empty
                gold_data = row.get(gold_column)
                if pd.notna(gold_data) and gold_data:
                    try:
                        # Parse the JSON string in the gold standard column
                        gold_json = json.loads(gold_data)
                        
                        # Check if this is the enhanced format (array of objects) or original format (object with 'relationships')
                        if isinstance(gold_json, list):
                            # Enhanced format
                            for entry in gold_json:
                                # Get the date information
                                date = entry.get('date')
                                if not date:
                                    continue
                                
                                # Process each diagnosis associated with this date
                                diagnoses = entry.get('diagnoses', [])
                                for diag in diagnoses:
                                    if 'diagnosis' in diag:
                                        gold_standard.append({
                                            'note_id': i,
                                            'diagnosis': str(diag['diagnosis']).lower(),
                                            'date': date  # Already in YYYY-MM-DD format
                                        })
                        # Original format with 'relationships' key
                        elif 'relationships' in gold_json and isinstance(gold_json['relationships'], list):
                            for rel in gold_json['relationships']:
                                if 'diagnosis' in rel and 'date' in rel:
                                    gold_standard.append({
                                        'note_id': i,
                                        'diagnosis': str(rel['diagnosis']).lower(),
                                        'date': rel['date'] # Assume date is already YYYY-MM-DD
                                    })
                        else:
                            print(f"Warning: Unrecognized gold standard format for row {i}")
                    except (json.JSONDecodeError, TypeError, KeyError) as e:
                        print(f"Warning: Could not parse gold standard for row {i}: {e}")
                
                pbar.update(1)
        
        print(f"Prepared gold standard with {len(gold_standard)} relationships.")
    else:
        print("No gold standard column found or specified. Evaluation metrics will not be calculated.")
    
    # Pre-extract entities from the text column
    print("Pre-extracting entities...")
    prepared_test_data = []
    
    with tqdm(total=len(df), desc="Processing annotations", unit="note") as pbar:
        for i, row in df.iterrows():
            # Get the text from the specified column
            text = str(row.get(text_column, ''))
            
            # Initialize entities as empty lists in case we can't get valid annotations
            entities = ([], [])
            
            # Check if we have pre-annotated entities in the CSV and if this is a non-synthetic data source
            use_annotations = diagnoses_column and dates_column and diagnoses_column in df.columns and dates_column in df.columns
            
            if use_annotations:
                # Get the annotations from the CSV
                diagnoses_data = row.get(diagnoses_column)
                dates_data = row.get(dates_column)
                
                if pd.notna(diagnoses_data) and pd.notna(dates_data):
                    try:
                        # Parse diagnoses annotations from JSON format
                        diagnoses_list = []
                        # Transform Python-style string to valid JSON before parsing
                        valid_diagnoses_json = transform_python_to_json(diagnoses_data)
                        disorders = json.loads(valid_diagnoses_json)
                        for disorder in disorders:
                            label = disorder.get('label', '')
                            start_pos = disorder.get('start', 0)
                            diagnoses_list.append((label.lower(), start_pos))
                        
                        # Parse dates annotations from JSON format
                        dates_list = []
                        # Transform Python-style string to valid JSON before parsing
                        valid_dates_json = transform_python_to_json(dates_data)
                        formatted_dates = json.loads(valid_dates_json)
                        for date_obj in formatted_dates:
                            parsed_date = date_obj.get('parsed', '')
                            original_date = date_obj.get('original', '')
                            start_pos = date_obj.get('start', 0)
                            dates_list.append((parsed_date, original_date, start_pos))
                        
                        # If we found entities, use them
                        if diagnoses_list or dates_list:
                            entities = (diagnoses_list, dates_list)
                            if i < 3:  # Just for debugging, show first few entities
                                print(f"Row {i} diagnoses: {diagnoses_list[:2]}...")
                                print(f"Row {i} dates: {dates_list[:2]}...")
                        
                        # Try to extract relative dates using LLM if enabled and we have a timestamp
                        if relative_date_extraction_enabled:
                            # Get the document timestamp
                            timestamp_str = row.get(timestamp_column)
                            
                            if pd.notna(timestamp_str) and timestamp_str:
                                try:
                                    # Parse the timestamp string into a datetime object
                                    # Try different formats
                                    document_timestamp = None
                                    timestamp_formats = [
                                        '%Y-%m-%d',              # 2023-10-26
                                        '%Y-%m-%d %H:%M:%S',     # 2023-10-26 15:30:45
                                        '%m/%d/%Y',              # 10/26/2023
                                        '%m/%d/%Y %H:%M:%S',     # 10/26/2023 15:30:45
                                        '%d-%b-%Y',              # 26-Oct-2023
                                        '%d %b %Y',              # 26 Oct 2023
                                        '%d/%m/%Y',              # 14/05/2025
                                    ]
                                    
                                    for format_str in timestamp_formats:
                                        try:
                                            document_timestamp = datetime.strptime(timestamp_str, format_str)
                                            break
                                        except ValueError:
                                            continue
                                    
                                    if document_timestamp:
                                        # Only print for a few rows to reduce output
                                        if i % 20 == 0 or i < 3:
                                            print(f"Extracting relative dates for row {i} using timestamp: {document_timestamp.strftime('%Y-%m-%d')}")
                                        
                                        # Extract relative dates using LLM
                                        relative_dates = extract_relative_dates_llm(text, document_timestamp, config)
                                        
                                        if relative_dates:
                                            # Append relative dates to existing dates list
                                            diagnoses_list, dates_list = entities
                                            combined_dates_list = dates_list + relative_dates
                                            
                                            # Update entities with combined dates
                                            entities = (diagnoses_list, combined_dates_list)
                                            
                                            # Convert relative dates to JSON for storage in CSV
                                            relative_dates_json = []
                                            for date_tuple in relative_dates:
                                                parsed_date, original_phrase, start_pos = date_tuple
                                                relative_dates_json.append({
                                                    "parsed": parsed_date,
                                                    "original": original_phrase,
                                                    "start": start_pos
                                                })
                                            
                                            # Store in the dataframe
                                            df.at[i, 'llm_extracted_dates'] = json.dumps(relative_dates_json)
                                            
                                            if i % 20 == 0 or i < 3:  # Reduce output, just show some samples
                                                print(f"Row {i} extracted {len(relative_dates)} relative dates")
                                    else:
                                        print(f"Warning: Could not parse timestamp '{timestamp_str}' for row {i}")
                                
                                except Exception as e:
                                    print(f"Error extracting relative dates for row {i}: {e}")
                            
                    except Exception as e:
                        print(f"Warning: Could not parse annotations for row {i}: {e}")
                        # Don't fall back to extraction for real data, just use empty entities
                else:
                    # For empty annotation fields, don't attempt extraction - use empty entities
                    if i < 3:  # Just for debugging, show first few
                        print(f"Row {i}: No annotations available, using empty entities")
            else:
                # For synthetic data or when annotations aren't available, we extract entities from text
                if config.DATA_SOURCE.lower() == 'synthetic':
                    entities = extract_entities(text)
                else:
                    if i < 3:  # Reduce output
                        print(f"Row {i}: Using pre-annotated entities from annotation columns")
            
            # Add to prepared data
            prepared_test_data.append({
                'note': text,
                'entities': entities
            })
            
            pbar.update(1)
    
    # Save the updated dataframe with the new column back to CSV
    if relative_date_extraction_enabled:
        print(f"Saving CSV with LLM extracted dates to {dataset_path}")
        df.to_csv(dataset_path, index=False)
    
    return prepared_test_data, gold_standard

# Helper function to run extraction process for a given extractor and data
def run_extraction(extractor, prepared_test_data):
    """
    Runs the extraction process for a given extractor on prepared data.

    Args:
        extractor: An initialized and loaded extractor object (subclass of BaseExtractor).
        prepared_test_data (list): List of dicts {'text': ..., 'entities': ...}.

    Returns:
        list: List of predicted relationships [{'note_id': ..., 'diagnosis': ..., 'date': ..., 'confidence': ...}].
    """
    print(f"Generating predictions using {extractor.name}...")
    all_predictions = []
    skipped_rels = 0
    for i, note_entry in enumerate(tqdm(prepared_test_data, desc=f"Processing with {extractor.name}", unit="note")):
        try:
            # Extract relationships using the provided extractor
            relationships = extractor.extract(note_entry['note'], entities=note_entry['entities'])
            for rel in relationships:
                # Ensure required keys exist and handle potential missing 'date' or 'diagnosis'
                raw_date = rel.get('date')
                raw_diagnosis = rel.get('diagnosis')
                if raw_date is None or raw_diagnosis is None:
                    print(f"Warning: Skipping relationship in note {i} due to missing 'date' or 'diagnosis'. Rel: {rel}")
                    skipped_rels += 1
                    continue

                # Parse date and normalize diagnosis
                parsed_date = parse_date_string(str(raw_date)) # Ensure string input
                normalized_diagnosis = str(raw_diagnosis).strip().lower() # Ensure string, strip, lower

                if parsed_date and normalized_diagnosis:
                    all_predictions.append({
                        'note_id': i,
                        'diagnosis': normalized_diagnosis,
                        'date': parsed_date,
                        'confidence': rel.get('confidence', 1.0) # Default confidence to 1.0 if missing
                    })
                else:
                    # Log if parsing failed but keys were present
                    # print(f"Debug: Skipping relationship in note {i} due to parsing failure. Raw Date: '{raw_date}', Raw Diag: '{raw_diagnosis}'")
                    skipped_rels += 1
        except Exception as e:
            # Log errors during extraction for a specific note
            print(f"Extraction error on note {i} for {extractor.name}: {e}")
            # Optionally, re-raise if you want errors to halt execution: raise e
            continue # Continue with the next note

    print(f"Generated {len(all_predictions)} predictions. Skipped {skipped_rels} potentially invalid relationships.")
    return all_predictions

def calculate_and_report_metrics(all_predictions, gold_standard, extractor_name, output_dir, total_notes_processed):
    """
    Compares predictions with gold standard, calculates metrics, prints results,
    and saves a confusion matrix plot.

    Args:
        all_predictions (list): List of predicted relationships (normalized by the caller).
                                Each dict must contain 'note_id', 'diagnosis', 'date' (YYYY-MM-DD).
        gold_standard (list): List of gold standard relationships (normalized).
                              Each dict must contain 'note_id', 'diagnosis', 'date' (YYYY-MM-DD).
        extractor_name (str): Name of the extractor being evaluated.
        output_dir (str): Directory to save evaluation outputs.
        total_notes_processed (int): The total number of notes processed by the extractor.

    Returns:
        dict: A dictionary containing calculated metrics.
    """
    if not gold_standard:
        print(f"  No gold standard data provided for {extractor_name} (processed {total_notes_processed} notes). Skipping metric calculation.")
        # Return zeroed metrics if no gold standard
        return {
            'precision': 0, 'recall': 0, 'f1': 0,
            'true_positives': 0, 'false_positives': 0, 'false_negatives': 0
        }

    # Identify the notes that have gold standard labels
    gold_note_ids = set(g['note_id'] for g in gold_standard)
    num_labeled_notes = len(gold_note_ids)

    if num_labeled_notes == 0:
        print(f"  No notes with gold standard labels found for {extractor_name} (processed {total_notes_processed} notes). Skipping metric calculation.")
        return {
            'precision': 0, 'recall': 0, 'f1': 0,
            'true_positives': 0, 'false_positives': 0, 'false_negatives': 0
        }
    
    print(f"  Evaluating metrics for {extractor_name} based on {num_labeled_notes} notes with gold standard labels (out of {total_notes_processed} notes processed).")

    # Filter predictions to include only those from labeled notes
    filtered_predictions = [p for p in all_predictions if p['note_id'] in gold_note_ids]
    
    if not filtered_predictions:
        print(f"  No predictions found for the {num_labeled_notes} labeled notes by {extractor_name}.")
        # If no predictions for labeled notes, TP and FP are 0. FN is total gold.
        true_positives = 0
        false_positives = 0
        false_negatives = len(gold_standard) # All gold items were missed
        pred_set = set()  # Empty set for reporting
        gold_set = set((g['note_id'], g['diagnosis'], g['date']) for g in gold_standard)
    else:
        # Convert filtered predictions and gold standard to sets for comparison
        pred_set = set((p['note_id'], p['diagnosis'], p['date']) for p in filtered_predictions)
        gold_set = set((g['note_id'], g['diagnosis'], g['date']) for g in gold_standard)

        # Calculate TP, FP, FN based on filtered predictions
        true_positives = len(pred_set & gold_set)
        false_positives = len(pred_set - gold_set)
        false_negatives = len(gold_set - pred_set)
    
    true_negatives = 0 # TN is ill-defined/hard to calculate accurately here

    # Calculate metrics
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # --- Reporting ---
    print(f"  Evaluation Results for {extractor_name} (on labeled subset):")
    print(f"    Total unique predictions for labeled notes: {len(pred_set)}")    # TP + FP for labeled notes
    print(f"    Total unique gold relationships:           {len(gold_set)}")   # TP + FN for labeled notes
    print(f"    True Positives:  {true_positives}")
    print(f"    False Positives: {false_positives}")
    print(f"    False Negatives: {false_negatives}")
    print(f"    Precision: {precision:.3f}")
    print(f"    Recall:    {recall:.3f}")
    print(f"    F1 Score:  {f1:.3f}")

    # --- Plotting ---
    # Plotting confusion matrix based on these filtered values
    conf_matrix_values = [true_negatives, false_positives, false_negatives, true_positives]
    plt.figure(figsize=(6, 5))
    tn, fp, fn, tp = conf_matrix_values
    conf_matrix_display_array = np.array([[tn, fp], [fn, tp]])
    disp = ConfusionMatrixDisplay(confusion_matrix=conf_matrix_display_array, display_labels=['No Relation (in labeled)', 'Has Relation (in labeled)'])
    disp.plot(cmap=plt.cm.Blues, values_format='d')
    plt.title(f"Confusion Matrix - {extractor_name} (Labeled Subset)")
    plt.tight_layout()

    os.makedirs(output_dir, exist_ok=True)
    safe_extractor_name = re.sub(r'[^\w.-]+', '_', extractor_name).lower()
    plot_filename = f"{safe_extractor_name}_confusion_matrix_labeled_subset.png"
    plot_save_path = os.path.join(output_dir, plot_filename)
    try:
        plt.savefig(plot_save_path)
        print(f"    Confusion matrix (labeled subset) saved to {plot_save_path}")
    except Exception as e:
        print(f"    Error saving confusion matrix: {e}")
    plt.close()

    # Return calculated metrics
    metrics_dict = {
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'true_positives': true_positives,
        'false_positives': false_positives,
        'false_negatives': false_negatives,
    }
    return metrics_dict

def transform_python_to_json(python_string):
    """
    Transform a Python-style string with single quotes and datetime objects 
    into a valid JSON string with double quotes.
    
    Args:
        python_string: A string representing Python objects (like a list of dicts with single quotes)
        
    Returns:
        A valid JSON string with all strings double-quoted
    """
    if not python_string or pd.isna(python_string):
        return "[]"  # Return empty JSON array if input is empty or NaN
        
    # Handle datetime.date objects by converting them to ISO format strings
    # Example: datetime.date(2019, 4, 18) -> "2019-04-18"
    date_pattern = r"datetime\.date\((\d+),\s*(\d+),\s*(\d+)\)"
    def date_replacer(match):
        year, month, day = map(int, match.groups())
        return f'"{year:04d}-{month:02d}-{day:02d}"'
    
    # Apply the datetime replacement
    python_string_cleaned = re.sub(date_pattern, date_replacer, python_string)
    
    try:
        # Use ast.literal_eval to safely parse the Python literal
        python_obj = ast.literal_eval(python_string_cleaned)
        
        # Convert to valid JSON string with double quotes
        return json.dumps(python_obj)
    except (SyntaxError, ValueError) as e:
        # If ast.literal_eval fails, return an empty JSON array
        print(f"Warning: Failed to parse Python-style string: {e}")
        return "[]"

def extract_relative_dates_llm(text, document_timestamp, config):
    """
    Extract relative date references from text using an LLM.
    Returns a list of tuples: (parsed_date_str, raw_phrase_str, start_position)
    compatible with the existing dates format.
    
    Args:
        text (str): The clinical note text
        document_timestamp (datetime): The timestamp of the document for reference
        config: Configuration object with LLM settings
        
    Returns:
        list: A list of date tuples (parsed_date_str, raw_phrase_str, start_position)
    """
    # Check if relative date extraction is enabled
    if not hasattr(config, 'ENABLE_RELATIVE_DATE_EXTRACTION') or not config.ENABLE_RELATIVE_DATE_EXTRACTION:
        return []
        
    # Check inputs
    if not text or pd.isna(text) or not document_timestamp:
        return []
    
    # Truncate text if longer than the configured context window
    max_context = getattr(config, 'RELATIVE_DATE_CONTEXT_WINDOW', 1000)
    if len(text) > max_context:
        text = text[:max_context]
    
    # Determine which LLM to use
    llm_model = getattr(config, 'RELATIVE_DATE_LLM_MODEL', 'openai')
    
    if llm_model.lower() == 'openai':
        return extract_relative_dates_openai(text, document_timestamp, config)
    elif llm_model.lower() == 'llama':
        return extract_relative_dates_llama(text, document_timestamp, config)
    else:
        print(f"Warning: Unknown RELATIVE_DATE_LLM_MODEL: {llm_model}")
        return []

def extract_relative_dates_openai(text, document_timestamp, config):
    """
    Extract relative dates using OpenAI API.
    
    Args:
        text (str): The clinical note text
        document_timestamp (datetime): The timestamp of the document for reference
        config: Configuration object with OpenAI settings
        
    Returns:
        list: A list of date tuples (parsed_date_str, raw_phrase_str, start_position)
    """
    try:
        # Load environment variables for API key
        load_dotenv()
        api_key = os.getenv('OPENAI_API_KEY')
        
        # Reduce verbosity
        debug_mode = getattr(config, 'DEBUG_MODE', False)
        if debug_mode:
            print("Attempting to use OpenAI API for relative date extraction...")
        
        if not api_key:
            print("Error: OPENAI_API_KEY not found in .env file or environment variables.")
            return []
        
        if api_key == "your_actual_api_key_here" or api_key == "your_api_key_here":
            print("Error: You need to replace the placeholder in .env with your actual OpenAI API key.")
            return []
            
        if debug_mode:
            print(f"API key found (starts with: {api_key[:4]}{'*' * 20})")
        
        # Import OpenAI
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            if debug_mode:
                print("OpenAI client initialized successfully")
        except ImportError:
            print("Error: openai package not installed. Install with 'pip install openai'.")
            return []
        
        # Get model name from config or use default
        model_name = getattr(config, 'RELATIVE_DATE_OPENAI_MODEL', 'gpt-3.5-turbo')
        if debug_mode:
            print(f"Using OpenAI model: {model_name}")
        
        # Format the timestamp for the prompt
        timestamp_str = document_timestamp.strftime('%Y-%m-%d %H:%M:%S')
        
        # Construct the prompt
        prompt = f"""
        Given the document creation date: {timestamp_str}

        Analyze the following clinical text and identify phrases that describe dates relative to the document creation date:
        "{text}"

        I need to extract all relative date references like:
        - "last year" 
        - "six months ago" 
        - "yesterday" 
        - "next week" 
        - "in 3 days"
        - "two years ago"
        - "last month"

        For each identified phrase:
        1. Extract the exact phrase text (e.g., "last year", "yesterday")
        2. Note the start character index of the phrase in the original text
        3. Calculate the absolute date in YYYY-MM-DD format

        Example 1:
        Text: "Patient was diagnosed with condition X last year."
        - Phrase: "last year"
        - Start index: (position in text)
        - Calculated date: (one year before document date)

        Example 2:
        Text: "Follow-up scheduled in two weeks."
        - Phrase: "in two weeks"
        - Start index: (position in text)
        - Calculated date: (two weeks after document date)

        Return a JSON array where each object has these keys:
        "phrase": the exact relative date phrase,
        "start_index": integer position in text,
        "calculated_date": YYYY-MM-DD format

        If no relative dates are found, return an empty JSON array [].
        """
        
        if debug_mode:
            print("Sending request to OpenAI API...")
        
        # Call the OpenAI API
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a medical AI assistant specialized in extracting temporal expressions from clinical notes."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                max_tokens=1000
            )
            if debug_mode:
                print("Received response from OpenAI API")
        except Exception as api_error:
            print(f"OpenAI API error: {api_error}")
            return []
        
        # Extract the response text
        response_text = response.choices[0].message.content.strip()
        if debug_mode:
            print(f"Response text length: {len(response_text)} characters")
            print(f"First 100 chars of response: {response_text[:100]}...")
        
        # Find the JSON array in the response
        start_idx = response_text.find('[')
        end_idx = response_text.rfind(']') + 1
        
        if start_idx >= 0 and end_idx > start_idx:
            json_str = response_text[start_idx:end_idx]
            if debug_mode:
                print(f"Found JSON array: {json_str[:100]}...")
            
            try:
                dates_data = json.loads(json_str)
                # Only print the count of dates found to reduce verbosity
                if dates_data:
                    if debug_mode:
                        print(f"Successfully parsed JSON with {len(dates_data)} results")
                
                # Convert to the expected tuple format
                relative_dates = []
                for item in dates_data:
                    phrase = item.get('phrase', '')
                    start_index = item.get('start_index', 0)
                    calculated_date = item.get('calculated_date', '')
                    
                    # Only add valid entries
                    if phrase and calculated_date:
                        relative_dates.append((calculated_date, phrase, start_index))
                
                return relative_dates
            except json.JSONDecodeError as e:
                print(f"Error parsing OpenAI JSON response: {e}")
                return []
        else:
            if debug_mode:
                print("No JSON array found in OpenAI response")
                if len(response_text) < 200:
                    print(f"Full response was: {response_text}")
            return []
            
    except Exception as e:
        print(f"Error in OpenAI relative date extraction: {e}")
        if getattr(config, 'DEBUG_MODE', False):
            import traceback
            traceback.print_exc()
        return []

def extract_relative_dates_llama(text, document_timestamp, config):
    """
    Extract relative dates using Llama model.
    
    Args:
        text (str): The clinical note text
        document_timestamp (datetime): The timestamp of the document for reference
        config: Configuration object with Llama settings
        
    Returns:
        list: A list of date tuples (parsed_date_str, raw_phrase_str, start_position)
    """
    try:
        # Check if transformers package is installed
        try:
            from transformers import pipeline
            import torch
        except ImportError:
            print("Error: transformers package not installed. Install with 'pip install transformers'.")
            return []
        
        # Get model path from config
        model_path = getattr(config, 'LLAMA_MODEL_PATH', './Llama-3.2-3B-Instruct')
        
        # Initialize the pipeline
        try:
            # Create a loading indicator since model loading can take time
            with tqdm(total=100, desc="Loading Llama model", unit="%") as pbar:
                print(f"Loading Llama model for relative date extraction from {model_path}...")
                
                # Update progress to 25% - started loading
                pbar.update(25)
                
                # Load the model
                pipe = pipeline(
                    "text-generation",
                    model=model_path,
                    torch_dtype=torch.bfloat16,
                    device_map="auto",
                )
                
                # Update progress to 100% - done loading
                pbar.update(75)
        except Exception as e:
            print(f"Error loading Llama model: {e}")
            return []
        
        # Format the timestamp for the prompt
        timestamp_str = document_timestamp.strftime('%Y-%m-%d %H:%M:%S')
        
        # Construct the messages for the model
        system_prompt = "You are a medical AI assistant specialized in extracting temporal expressions from clinical notes."
        
        user_prompt = f"""
        Given the document creation date: {timestamp_str}

        Analyze the following clinical text and identify phrases that describe dates relative to the document creation date:
        "{text}"

        I need to extract all relative date references like:
        - "last year" 
        - "six months ago" 
        - "yesterday" 
        - "next week" 
        - "in 3 days"
        - "two years ago"
        - "last month"

        For each identified phrase:
        1. Extract the exact phrase text (e.g., "last year", "yesterday")
        2. Note the start character index of the phrase in the original text
        3. Calculate the absolute date in YYYY-MM-DD format

        Example 1:
        Text: "Patient was diagnosed with condition X last year."
        - Phrase: "last year"
        - Start index: (position in text)
        - Calculated date: (one year before document date)

        Example 2:
        Text: "Follow-up scheduled in two weeks."
        - Phrase: "in two weeks"
        - Start index: (position in text)
        - Calculated date: (two weeks after document date)

        Return a JSON array where each object has these keys:
        "phrase": the exact relative date phrase,
        "start_index": integer position in text,
        "calculated_date": YYYY-MM-DD format

        If no relative dates are found, return an empty JSON array [].
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Run inference with the model
        outputs = pipe(
            messages,
            max_new_tokens=1000,
            do_sample=False,
            temperature=None,
        )
        
        # Extract response content
        response_content = ""
        try:
            # Get the last message from the generated conversation
            last_message = outputs[0]["generated_text"][-1]
            
            # The last message should be a dict with the assistant's response
            if isinstance(last_message, dict) and "content" in last_message:
                response_content = last_message["content"].strip()
            else:
                # If it's not a dict with content, try to use it directly
                response_content = str(last_message).strip()
        except (IndexError, KeyError, AttributeError) as e:
            print(f"Error extracting response from Llama model output: {e}")
            return []
        
        # Extract JSON from the response
        start_idx = response_content.find('[')
        end_idx = response_content.rfind(']') + 1
        
        if start_idx >= 0 and end_idx > start_idx:
            json_str = response_content[start_idx:end_idx]
            
            try:
                dates_data = json.loads(json_str)
                
                # Convert to the expected tuple format
                relative_dates = []
                for item in dates_data:
                    phrase = item.get('phrase', '')
                    start_index = item.get('start_index', 0)
                    calculated_date = item.get('calculated_date', '')
                    
                    # Only add valid entries
                    if phrase and calculated_date:
                        relative_dates.append((calculated_date, phrase, start_index))
                
                return relative_dates
            except json.JSONDecodeError as e:
                print(f"Error parsing Llama JSON response: {e}")
                return []
        else:
            print("No JSON array found in Llama response")
            return []
    
    except Exception as e:
        print(f"Error in Llama relative date extraction: {e}")
        return []