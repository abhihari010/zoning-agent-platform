# Evidence Grading

Grade each evidence chunk for relevance and reliability.

## Input
- Query context: {query_context}
- Chunk: {chunk_text}
- Source metadata: {source_metadata}

## Output (JSON per chunk)
- relevance: 0.0 to 1.0
- reliability: "official" | "interpretive" | "unknown"
- applicable: boolean
