import os
import sys
import json
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from sklearn.model_selection import train_test_split

# Adjust relative paths for imports since train.py is in model_training/
# Get the parent directory (project root)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# Import from our modules using adjusted paths
# Files within the same directory (model_training)
from DiagnosisDateRelationModel import DiagnosisDateRelationModel 
from model_training.Vocabulary import Vocabulary 
import training_config 

# Files from other top-level directories
from data.ClinicalNoteDataset import ClinicalNoteDataset
from data.synthetic_data_generator import generate_dataset
from utils.training_utils import load_and_prepare_data
from utils.training_utils import train_model, plot_training_curves
from config import DEVICE, DATASET_PATH, MODEL_PATH, VOCAB_PATH 

def train():
    print(f"Using device: {DEVICE}")
    
    # Ensure the training directory exists for outputs
    model_full_path = os.path.join(project_root, MODEL_PATH)
    vocab_full_path = os.path.join(project_root, VOCAB_PATH) # Use updated config path
    output_dir = os.path.dirname(model_full_path) 
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Step 1: Generate or load dataset
    dataset_full_path = os.path.join(project_root, DATASET_PATH)
    if os.path.exists(dataset_full_path):
        print(f"Loading existing dataset from {dataset_full_path}")
        with open(dataset_full_path, 'r') as f:
            full_dataset = json.load(f)
            
        # Calculate the split point without shuffling - use 80% for training
        train_size = int(len(full_dataset) * 0.8)
        # Use only the first 80% for training
        dataset = full_dataset[:train_size]
        print(f"Using first {train_size}/{len(full_dataset)} samples (80%) for training")
    else:
        # Use NUM_SAMPLES from training_config
        print(f"Generating synthetic clinical notes dataset with {training_config.NUM_SAMPLES} samples...") 
        dataset = generate_dataset(num_notes=training_config.NUM_SAMPLES)
        os.makedirs(os.path.dirname(dataset_full_path), exist_ok=True)
        with open(dataset_full_path, 'w') as f:
            json.dump(dataset, f, indent=2)
    
    print(f"Training dataset contains {len(dataset)} clinical notes")
    
    # Step 2: Prepare data for model training
    print("Loading and preparing data...")
    # Use training_config settings here
    features, labels, vocab_instance = load_and_prepare_data(
        dataset, training_config.MAX_DISTANCE, Vocabulary
    )
    print(f"Loaded {len(features)} examples with vocabulary size {vocab_instance.n_words}")
    
    # Save vocabulary to the path defined in config (now model_training/vocab.pt)
    # Ensure the directory exists (it should as it's the same as output_dir)
    os.makedirs(os.path.dirname(vocab_full_path), exist_ok=True)
    torch.save(vocab_instance, vocab_full_path) 
    print(f"Saved vocabulary to {vocab_full_path}")
    
    # Check class balance
    if len(labels) > 0:
        positive = sum(labels)
        negative = len(labels) - positive
        print(f"Class distribution: {positive} positive examples ({positive/len(labels)*100:.1f}%), {negative} negative examples ({negative/len(labels)*100:.1f}%)")
    else:
        print("Warning: No examples found in the dataset!")
        sys.exit(1)  # Use sys.exit
    
    # Step 3: Create train / val / test datasets 
    # Note: These are splits within the training portion (80%) of the data
    train_features, val_features, train_labels, val_labels = train_test_split(
        features, labels, test_size=0.2, random_state=42
    )
    
    print(f"Train: {len(train_features)}, Validation: {len(val_features)}")
    
    # Create datasets using training_config settings
    train_dataset = ClinicalNoteDataset(
        train_features, train_labels, vocab_instance, 
        training_config.MAX_CONTEXT_LEN, training_config.MAX_DISTANCE
    ) 
    val_dataset = ClinicalNoteDataset(
        val_features, val_labels, vocab_instance, 
        training_config.MAX_CONTEXT_LEN, training_config.MAX_DISTANCE
    )
    
    # Create data loaders using training_config batch size
    train_loader = DataLoader(train_dataset, batch_size=training_config.BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=training_config.BATCH_SIZE)
    
    # Step 4: Initialize and train model using training_config settings
    model = DiagnosisDateRelationModel(
        vocab_size=vocab_instance.n_words, 
        embedding_dim=training_config.EMBEDDING_DIM,
        hidden_dim=training_config.HIDDEN_DIM
    ).to(DEVICE)
    
    # Loss function and optimizer using training_config learning rate
    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=training_config.LEARNING_RATE)
    
    # Train model using training_config epochs
    print("Training model...")
    train_losses, val_losses, val_accs = train_model(
        model, train_loader, val_loader, optimizer, criterion, 
        training_config.NUM_EPOCHS, DEVICE, model_full_path
    )
    
    # Plot training curves
    plot_save_path = os.path.join(output_dir, 'training_curves.png')
    plot_training_curves(train_losses, val_losses, val_accs, plot_save_path)
    
    print("Done!")

if __name__ == "__main__":
    train() 