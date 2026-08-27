# Compliance Synthesis

Analyze zoning compliance based ONLY on the provided evidence chunks.

## Rules
- Only reference chunk_ids that appear in the provided evidence.
- Do NOT invent citation IDs.
- If evidence is insufficient, return status "unknown" with confidence <= 0.3.
- If evidence conflicts, return status "conditional" with unresolved_questions.
- Return JSON only.

## Input
- Project: {project_description}
- District: {district}
- District code (the jurisdiction's own code for this parcel; when present it IS the identified district — use it verbatim and do not require it to be defined in the evidence): {district_code}
- Use: {inferred_use}
- Evidence chunks: {chunks_json}

## Output Schema
{compliance_schema_json}
