import numpy as np
import json
import os

def load_previous_vector(file_path):
    """
    Load the previous speaker vector from file.
    """
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            prev_vector = json.load(file)
        return np.array(prev_vector)
    else:
        return None


def update_speaker_signature(new_vector, prev_vector, buffer_size=100):
    """
    Update the speaker signature by averaging the new vector with the old one.

    :param new_vector: The new x-vector collected.
    :param prev_vector: The previous x-vector (or average of all past vectors).
    :param buffer_size: Number of vectors to use in the average.
    :return: The updated vector.
    """
    if prev_vector is not None:
        # Calculate the updated average vector
        updated_vector = (prev_vector + new_vector) / 2
    else:
        updated_vector = new_vector
    return updated_vector


def save_speaker_signature(updated_vector, file_path):
    """
    Save the updated speaker signature to a file.
    """
    with open(file_path, "w") as file:
        json.dump(updated_vector.tolist(), file)
    print("Speaker signature updated and saved to", file_path)


# Usage
file_path = "vector.txt"

# Load previous vector (if exists)
prev_vector = load_previous_vector(file_path)
new_vector = load_previous_vector("vector2.txt")
# Assuming you have a new x-vector to update
new_xvector = np.array(new_vector)  # Replace this with the actual new vector

# Update the speaker signature
updated_vector = update_speaker_signature(new_xvector, prev_vector)

# Save the updated vector
save_speaker_signature(updated_vector, file_path)
