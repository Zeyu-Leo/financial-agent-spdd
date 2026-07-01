"""Versioned SQL DDL files for the project.

Schema is parameterised on the embedding dimension. The ingest scripts
substitute `/* EMBEDDING_DIM */` at apply time with the configured value.
"""
