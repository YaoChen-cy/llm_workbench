"""
Usage
  python run.py --month 2026-10            # all PDFs in input/2026-10/
  python run.py --pdf path/to/memo.pdf     # a single PDF
  python run.py --dump-source memo.pdf     # print the parsed text with IDs (to build few-shot examples)
"""
import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import config
import export
from parse import guess_company_name, parse_pdf
from summarize import summarize
from verify import verify


def process(pdf: Path, out_dir: Path) -> dict:
    t0 = time.time()
    company = pdf.stem.replace("_", " ")
    try:
        parsed = parse_pdf(pdf)
        company = guess_company_name(parsed, company)
        if not parsed.paragraphs:
            raise ValueError("no text found after 'Company Overview' — check SECTIONS in config.py")
        summary = verify(summarize(parsed), parsed)

        stem = re.sub(r"[^\w\-]+", "_", company).strip("_")
        export.write_docx(company, summary, parsed, out_dir / f"{stem}_summary.docx")
        if config.WRITE_HIGHLIGHTED_PDF:
            export.write_highlighted_pdf(summary, parsed, out_dir / f"{stem}_cited.pdf")
        (out_dir / f"{stem}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

        n_flag = sum(p.get("flagged", False) for part in export.PART_TITLES for p in summary.get(part, []))
        warn = f"  missing sections: {parsed.missing_sections}" if parsed.missing_sections else ""
        print(f"  ✓ {company}: {time.time() - t0:.0f}s, {n_flag} point(s) flagged{warn}")
        return {"company": company, "parsed": parsed, "summary": summary}
    except Exception as e:
        print(f"  ✗ {company}: {e}")
        return {"company": company, "error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month")
    ap.add_argument("--pdf")
    ap.add_argument("--dump-source")
    args = ap.parse_args()

    if args.dump_source:
        print(parse_pdf(args.dump_source).to_prompt_text())
        return

    if args.pdf:
        pdfs, tag = [Path(args.pdf)], Path(args.pdf).stem
    elif args.month:
        pdfs, tag = sorted((config.INPUT_DIR / args.month).glob("*.pdf")), args.month
    else:
        ap.error("give --month or --pdf")
    if not pdfs:
        ap.error("no PDFs found")

    out_dir = config.OUTPUT_DIR / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Processing {len(pdfs)} PDF(s) -> {out_dir}  [LLM_MODE={config.LLM_MODE}]")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as pool:
        results = list(pool.map(lambda p: process(p, out_dir), pdfs))

    export.write_review_xlsx(results, out_dir / "review_checklist.xlsx")
    print(f"Done in {time.time() - t0:.0f}s. Review: {out_dir / 'review_checklist.xlsx'}")


if __name__ == "__main__":
    main()
