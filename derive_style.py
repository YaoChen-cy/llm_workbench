"""
Step 2 of prompt tuning: let the LLM read many human summaries and draft a house style guide.

    python derive_style.py        ->  prompts/style_guide.draft.md   (review, edit, then rename to style_guide.md)

Reads every eval/<case>/human_summary.md and prompts/examples/<case>/summary.md.
"""
import config
from llm_client import call_llm


def main():
    files = sorted(config.EVAL_DIR.glob("*/human_summary.md")) + sorted(config.EXAMPLES_DIR.glob("*/summary.md"))
    if not files:
        raise SystemExit("No human summaries found in eval/*/human_summary.md or prompts/examples/*/summary.md")
    summaries = "\n\n".join(f"--- Summary {i} ---\n{f.read_text(encoding='utf-8').strip()}"
                            for i, f in enumerate(files, 1))
    prompt = (config.PROMPT_DIR / "meta" / "derive_style_guide.md").read_text(encoding="utf-8")
    prompt = prompt.replace("{n}", str(len(files))).replace("{summaries}", summaries)

    guide = call_llm("You are a precise technical editor.", prompt, task="style")
    out = config.PROMPT_DIR / "style_guide.draft.md"
    out.write_text(guide, encoding="utf-8")
    print(f"Read {len(files)} summaries -> {out}\nReview it, edit, then replace prompts/style_guide.md.")


if __name__ == "__main__":
    main()
