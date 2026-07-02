"""
Populates a local Chroma collection with a handful of docs, embedded with
the same HuggingFace model the pipeline.yaml in this folder uses — so
`rag-debug run` has something real to retrieve against.

This only needs to be run ONCE (or whenever you want to reset the demo
corpus). It requires: pip install chromadb sentence-transformers
"""

import chromadb
from sentence_transformers import SentenceTransformer

DOCS = [
    ("doc1", "To reset your password, go to Settings, then Security, then "
             "click Reset Password. You'll receive an email with a reset "
             "link valid for 24 hours."),
    ("doc2", "Our refund policy: refunds are processed within 5 business "
             "days of the request being submitted through the billing "
             "portal. Partial refunds are not available."),
    ("doc3", "The Enterprise plan includes single sign-on (SSO) support "
             "via SAML 2.0, integrating with Okta, Azure AD, and Google "
             "Workspace."),
    ("doc4", "API rate limits on the free tier are 100 requests per "
             "minute and 10,000 requests per day. Paid tiers have higher "
             "limits — see the pricing page."),
    ("doc5", "Two-factor authentication can be enabled from Settings > "
             "Security > Two-Factor Auth. We support both SMS and "
             "authenticator apps like Google Authenticator."),
]

print("Loading embedding model (all-MiniLM-L6-v2, first run downloads ~90MB)...")
model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

print("Connecting to local Chroma (./chroma_data)...")
client = chromadb.PersistentClient(path="./chroma_data")
collection = client.get_or_create_collection(name="demo_docs")

ids = [doc_id for doc_id, _ in DOCS]
texts = [text for _, text in DOCS]
embeddings = model.encode(texts, convert_to_numpy=True).tolist()

collection.upsert(ids=ids, documents=texts, embeddings=embeddings)
print(f"Seeded {len(DOCS)} documents into 'demo_docs' collection.")
print("You can now run: rag-debug run --config pipeline.yaml --queries queries.json")
