# overrides.json: what the model writes

The report numbers come from `facts.json`. `overrides.json` holds only judgment, so the same data always produces the same
numbers. Every key is optional. Keep the language plain and customer-facing. Never use em dashes.

```json
{
  "summary": "Two or three sentences for the executive summary. Lead with the finding and the size of it.",
  "summary_points": ["One line each, 3 to 5 of them, each traceable to the digest."],
  "priorities": ["Ordered actions, most valuable and cheapest first."],
  "opportunity_notes": {
    "O1": "Context only the model knows, for example which teams own the unused families.",
    "O5": "Which probed metrics are safe to lengthen first."
  },
  "extra_findings": [
    {"title": "A finding the standard set does not cover", "text": "Evidence and meaning.", "steps": ["Step 1", "Step 2"]}
  ],
  "caveats": ["Anything the customer should know about the data, for example a 403 on a settings schema."],
  "phases": [
    {"name": "Phase 1: ...", "goal": "...", "steps": ["..."], "owners": "...", "effort": "Low", "outcome": "..."}
  ]
}
```

Rules:
- Every number in the text must come from `digest.md` or `facts.json`. Check each one before writing it.
- `phases` replaces the default plan. Leave it out unless the default does not fit.
- Write for the customer. Method detail belongs in the appendix, which the generator already writes.
- Do not name a person as the cause of anything. Describe the configuration.
- Do not repeat what the appendix already says (90 day usage window, detector runs excluded, wildcard handling, dollar rate). Add only what is specific to this tenant.
- If a collection step failed (see "Collection errors" in the digest), say what is missing in `caveats`.
