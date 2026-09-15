"""
vivy_env.py
===========
Globally injects environment overrides to force AI libraries (transformers, torch, ctranslate2)
to cache their massive files on the D: drive instead of C: drive.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "model_cache")

HF_HOME = os.path.join(CACHE_DIR, "huggingface")
TORCH_HOME = os.path.join(CACHE_DIR, "torch")

os.environ["HF_HOME"] = HF_HOME
os.environ["TORCH_HOME"] = TORCH_HOME

# Some older transformer versions respect these explicitly:
os.environ["TRANSFORMERS_CACHE"] = os.path.join(HF_HOME, "hub")
os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(HF_HOME, "hub")

# Ensure they exist (we will physically move the files here shortly)
os.makedirs(HF_HOME, exist_ok=True)
os.makedirs(TORCH_HOME, exist_ok=True)
