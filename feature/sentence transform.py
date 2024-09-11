from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("all-MiniLM-L6-v2")


# Compute embeddings for both lists

# Compute cosine similarities
embeddings1 = model.encode(["Turn on the lights"])
embeddings2 = model.encode(["Turn the lights on"])

similarities = float(model.similarity(embeddings1, embeddings2))
