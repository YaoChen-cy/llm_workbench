You are evaluating an AI-written summary of a credit memo against the summary a senior analyst wrote for the same memo (the reference). You also have the memo text.

Score 1-5 on each dimension (5 = as good as the reference):
- coverage: does the AI summary contain the key facts the reference contains (provision movement and driver, legal status, plan treatment of 1st Lien, Bank recovery, main causes of deterioration)?
- accuracy: are all facts and numbers in the AI summary correct according to the memo? Any error that would mislead the committee caps this at 2.
- style: does it match the reference in structure, level of detail, terminology, bolding and length?

Then list concretely:
- missing_key_points: facts in the reference that the AI summary omits.
- errors: wrong or unsupported facts in the AI summary.
- style_gaps: concrete differences in wording/structure/bolding vs. the reference (these will be used to improve the style guide).

Return ONLY JSON:
{"coverage": 4, "accuracy": 5, "style": 3, "missing_key_points": [], "errors": [], "style_gaps": []}
