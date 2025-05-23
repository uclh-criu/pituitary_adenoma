# Training Configuration for the Custom PyTorch Model

# Model Architecture Parameters
EMBEDDING_DIM = 128
HIDDEN_DIM = 256

# Training Hyperparameters
LEARNING_RATE = 0.001
NUM_EPOCHS = 15
BATCH_SIZE = 16

# Data Processing Parameters (used during training data prep)
# Max char distance between entities to consider when creating training examples
MAX_DISTANCE = 500
# Max sequence length for context fed into the model
MAX_CONTEXT_LEN = 512 

# Dataset Generation (if dataset needs to be created)
NUM_SAMPLES = 100 # Number of synthetic notes to generate 