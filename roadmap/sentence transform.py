from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")


# Compute embeddings for both lists
embeddings1 = model.encode(["Stewart turn on the lights and enable some music"])
embeddings2 = model.encode(["Stewart enable the lights and turn on some music", "Stewart keep the lights on and turn off the music"])

# Compute cosine similarities
similarities = model.similarity(embeddings1, embeddings2)

print(similarities)