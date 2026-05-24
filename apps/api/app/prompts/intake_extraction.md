# Intake Extraction

Extract structured information from the project description.

## Input
- Project description: {project_description}
- Address: {address}
- Jurisdiction: {jurisdiction_id}

## Output (JSON)
- inferred_use: string
- district_guess: string or null
- scope: "new_construction" | "renovation" | "change_of_use" | "expansion" | "unknown"
- key_features: list of strings
