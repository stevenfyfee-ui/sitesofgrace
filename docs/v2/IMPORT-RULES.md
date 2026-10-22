# Import rules for v2 content

Every v2 JSON import command follows these rules. They are the rules the October 2026 travel
import (`import_travel_sections`) proved out, plus Standing Rule 4 (never overwrite a filled field
from code). `import_site_details` is the first command written against this file.

## File

- UTF-8 JSON with a top-level `"pages"` list. One object per page.
- The command takes a path that goes through `glob.glob` (so `tools/*site_details*.json` works in the
  DigitalOcean console) and must match **exactly one** file.

## Matching

1. **Match on page ID only** — never on slug or title. The row's `title` must equal the page's
   current title; a mismatch is skipped and reported (it means the ID points at the wrong page).
2. **Only rows whose `status` is `"Ready to import"`** are considered. Any other status is skipped
   and counted, so a half-finished spreadsheet can be exported safely.

## Values

3. **Blank means no change.** An empty string, `null` or a missing key leaves the field alone. There is
   no way to clear a field through an import; clear it in the admin.
4. **Never overwrite a filled field.** If the page already has a different value, the row is a
   **conflict** and the whole page is skipped and reported. The same value counts as already correct.
5. **Lengths come from the model** (`_meta.get_field(name).max_length`), never from a number in the
   file or the command. A value that is too long is **rejected, not truncated** — the whole page is
   skipped.
6. Choice fields accept the stored value or its label; anything else is rejected. URLs must
   validate. Rich text must parse as balanced HTML using only tags the editor supports. Whole
   numbers must be whole numbers in range.
7. Field names must be on the command's allowed list; an unknown field skips the page.
8. Everything for a page is validated **before** anything is written. One bad value skips the page.

## Writing

9. A page with **unpublished changes (a draft)** is skipped: publishing would either lose the draft or
   publish it. A page that **isn't live** is skipped: publishing would make it public.
10. A page that changes gets **one new revision**, published with
    `save_revision(log_action=True).publish()` inside `transaction.atomic()`, so the admin history
    shows the import.
11. A page with nothing to change gets **no revision**, which is why a **second run reports 0 changed**.

## Modes and report

12. `--dry-run` does all reading, validation and comparison and prints the same report, writing
    nothing.
13. `--verify` writes nothing and checks the database against the file value by value; it exits with an
    error if any page does not match. It is the proof an import ran, not just that it was quiet.
14. The report prints one line per changed page, then totals: changed, unchanged / already correct,
    fields set, conflicts and skipped — each skipped or conflicting page with its reason.
