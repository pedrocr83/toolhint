You grade one output of a benchmark task. Score it from 1 to 10 against the task and the reference.

- The reference shows what a strong answer covers. It may be out of date or incomplete: do not penalize additional facts that are correct and sourced, or a different structure that serves the reader as well.
- Judge correctness first, then completeness against what the task asked for, then clarity. Ignore tone and style preferences.
- 10: correct, complete, and clear. 7: correct with minor gaps. 4: notable errors or missing key points. 1: missing, wrong, or off task.

Reply with only a JSON object: {"score": <integer 1-10>, "reason": "<one sentence>"}

<task>
{{task}}
</task>

<reference>
{{reference}}
</reference>

<output>
{{output}}
</output>
