"""Import approved Future Saints learning pages from JSON, as drafts.

    python manage.py import_learning_pages docs/future-saints/content/carlo-acutis.json --dry-run
    python manage.py import_learning_pages docs/future-saints/content/carlo-acutis.json
    python manage.py import_learning_pages docs/future-saints/content/carlo-acutis.json --verify

Format "future-saints-learning-pages/v1": {"format", "approved_by", "approved_on", "pages": [...]}.
Follows docs/v2/IMPORT-RULES.md where it applies (one file per glob; lengths from the model,
rejected never truncated; everything validated before anything is written; --dry-run and
--verify; a second run reports 0 changed). Two deliberate differences: it NEVER publishes or
submits to the review workflow (an editor does that in the admin), and the JSON is the approved
source for the whole page, so an update replaces the page's content in a new draft revision
(rules 3-4, written for filling canonical pages, don't apply).

Per page:
- Parent: the Future Saints index with slug "parent_index" whose content_kind is "kind".
- Canonical link: "canonical.model" with exactly one LIVE page titled "match_title".
  "production_id_hint" is only cross-checked and reported, never used to link.
- New page: created unpublished, with one draft revision. Existing page with no unpublished
  changes: a new draft revision. Existing page WITH unpublished changes (a draft): skipped.
  Unchanged content: no revision ("0 changed").
- Text is escaped; no HTML is accepted from the JSON. story_paragraphs and intro become <p>s.
- Structural mappings only (no text is ever changed): semantic inherit names to the model's
  QuickFact inherit keys, icon names to the model's icons, story_label to the saint choice.
"""
import glob
import json
import re

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator
from django.db import transaction
from django.utils.html import escape

from catalog.models import SacredSitePage, SaintPage
from future_saints.learning import SAINT_SOURCES, SITE_SOURCES, STORY_HEADING_CHOICES, _canonical_value
from future_saints.models import (
    EucharisticLearningPage,
    FunFact,
    FutureSaintsHomePage,
    FutureSaintsIndexPage,
    HolyLandLearningPage,
    MarianLearningPage,
    MissionLearningPage,
    QuickFact,
    QuizChoice,
    QuizQuestion,
    SaintLearningPage,
    SourceLink,
    TimelineEntry,
    WordToKnow,
)

FORMAT = "future-saints-learning-pages/v1"
QUIZ_LENGTH = 5
INTRO_WORDS = (50, 80)
STORY_WORDS = (250, 400)

KIND_MODELS = {
    "saint": SaintLearningPage,
    "marian_apparition": MarianLearningPage,
    "eucharistic_miracle": EucharisticLearningPage,
    "holy_land": HolyLandLearningPage,
    "california_mission": MissionLearningPage,
}
CANONICAL_MODELS = {"catalog.SaintPage": SaintPage, "catalog.SacredSitePage": SacredSitePage}

# Semantic inherit names in the JSON -> the model's QuickFact.inherit keys, by page family.
SAINT_INHERIT = {
    "life_dates": "saint_lived", "born": "saint_born", "died": "saint_died", "feast_day": "saint_feast",
    "canonized": "saint_canonized", "patronage": "saint_patronage", "religious_order": "saint_order",
    "burial_place": "saint_burial",
}
SITE_INHERIT = {
    "place": "site_place", "country": "site_country", "date": "site_date", "feast_day": "site_feast",
    "church_status": "site_status", "recognition_year": "site_recognition_year",
}
# JSON icon names that differ from the model's icon keys.
ICON_ALIASES = {"calendar-cross": "feast"}

PAGE_KEYS = {
    "kind", "parent_index", "slug", "canonical", "student_title", "subtitle", "story_label", "intro",
    "story_paragraphs", "quick_facts", "timeline", "fun_facts", "words_to_know", "think_about_it",
    "reflection_question", "kindness_prompt", "quiz", "sources",
}
SAINT_ONLY_KEYS = {"kindness_prompt"}
GRADE_WORDING = re.compile(r"\bgrades?\s*[0-9k]|\bgrade[- ]level\b|\breading level\b", re.IGNORECASE)


class PageError(Exception):
    """One page fails validation; nothing for it is written."""


def _words(text):
    return len(re.findall(r"\S+", text or ""))


def _paragraphs(texts):
    return "".join(f"<p>{escape(t)}</p>" for t in texts)


def _check_length(errors, model, field, value, where):
    limit = model._meta.get_field(field).max_length
    if limit and len(value) > limit:
        errors.append(f"{where}: {len(value)} characters, but {model.__name__}.{field} allows {limit}")


class Command(BaseCommand):
    help = "Import approved Future Saints learning pages from JSON as drafts (never publishes)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="A path or glob that matches exactly one JSON file.")
        parser.add_argument("--dry-run", action="store_true", help="Validate and report; write nothing.")
        parser.add_argument("--verify", action="store_true",
                            help="Compare each page's latest revision with the file; write nothing.")

    # --- entry ---------------------------------------------------------------
    def handle(self, *args, **options):
        if options["dry_run"] and options["verify"]:
            raise CommandError("Use --dry-run or --verify, not both.")
        matches = sorted(glob.glob(options["path"]))
        if len(matches) != 1:
            raise CommandError(f"{options['path']!r} matches {len(matches)} files; it must match exactly one.")
        path = matches[0]
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise CommandError(f'{path}: "format" must be "{FORMAT}".')
        pages = data.get("pages")
        if not isinstance(pages, list) or not pages:
            raise CommandError(f'{path}: "pages" must be a non-empty list.')

        mode = "VERIFY" if options["verify"] else ("DRY RUN" if options["dry_run"] else "IMPORT")
        self.stdout.write(f"{mode}: {path} ({len(pages)} page(s); approved by {data.get('approved_by', '?')} "
                          f"on {data.get('approved_on', '?')}). Nothing is published.")
        totals = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0, "failed": 0, "differences": 0}
        for i, row in enumerate(pages):
            label = f"page {i + 1} ({row.get('slug', '?') if isinstance(row, dict) else '?'})"
            try:
                plan = self.plan(row)
            except PageError as exc:
                totals["failed"] += 1
                self.stdout.write(self.style.ERROR(f"FAILED {label}:"))
                for line in str(exc).split("\n"):
                    self.stdout.write(f"  - {line}")
                continue
            if options["verify"]:
                totals["differences"] += self.verify(plan)
            else:
                totals[self.apply(plan, dry_run=options["dry_run"])] += 1

        if options["verify"]:
            self.stdout.write(f"Verify: {totals['differences']} difference(s); {totals['failed']} page(s) failed validation.")
            if totals["differences"] or totals["failed"]:
                raise CommandError("Verify found differences or failures.")
            self.stdout.write(self.style.SUCCESS("Verify: 0 differences."))
            return
        changed = totals["created"] + totals["updated"]
        self.stdout.write(
            f"{'Would change' if options['dry_run'] else 'Changed'}: {changed} "
            f"(created {totals['created']}, updated {totals['updated']}); unchanged {totals['unchanged']}; "
            f"skipped {totals['skipped']}; failed {totals['failed']}."
        )
        if totals["failed"]:
            raise CommandError(f"{totals['failed']} page(s) failed validation; nothing was written for them.")

    # --- validation and the desired page ------------------------------------
    def plan(self, row):
        errors = []
        if not isinstance(row, dict):
            raise PageError("each page must be a JSON object")
        unknown = set(row) - PAGE_KEYS
        if unknown:
            errors.append(f"unknown key(s): {', '.join(sorted(unknown))} (not imported; nothing is dropped silently)")
        kind = row.get("kind")
        model = KIND_MODELS.get(kind)
        if model is None:
            raise PageError(f'"kind" must be one of {", ".join(KIND_MODELS)} (got {kind!r})')
        for key in SAINT_ONLY_KEYS & set(row):
            if model is not SaintLearningPage:
                errors.append(f'"{key}" exists only on saint pages (this page is {kind})')
        for key in ("parent_index", "slug", "canonical", "student_title", "intro", "story_paragraphs", "quiz"):
            if not row.get(key):
                errors.append(f'"{key}" is required')
        if errors:
            raise PageError("\n".join(errors))

        parent = self._parent(row, kind, errors)
        canonical, hint_note = self._canonical(row, model, errors)
        scalars, children = self._desired(row, model, errors)
        if errors:
            raise PageError("\n".join(errors))
        warnings = []
        intro_words = _words(row.get("intro"))
        story_words = sum(_words(p) for p in row.get("story_paragraphs", []))
        if not INTRO_WORDS[0] <= intro_words <= INTRO_WORDS[1]:
            warnings.append(f"intro is {intro_words} words (target {INTRO_WORDS[0]}–{INTRO_WORDS[1]})")
        if not STORY_WORDS[0] <= story_words <= STORY_WORDS[1]:
            warnings.append(f"story is {story_words} words (target {STORY_WORDS[0]}–{STORY_WORDS[1]})")
        scalars["canonical_id"] = canonical.pk
        return {
            "row": row, "model": model, "parent": parent, "canonical": canonical, "hint_note": hint_note,
            "scalars": scalars, "children": children, "warnings": warnings,
            "words": (intro_words, story_words),
        }

    def _parent(self, row, kind, errors):
        home = FutureSaintsHomePage.objects.first()
        if home is None:
            errors.append("there is no Future Saints home page (run create_future_saints_tree)")
            return None
        parent = FutureSaintsIndexPage.objects.child_of(home).filter(slug=row["parent_index"]).first()
        if parent is None:
            errors.append(f'no Future Saints index with slug "{row["parent_index"]}" under {home.url_path}')
        elif parent.content_kind != kind:
            errors.append(f'index "{parent.slug}" is for {parent.content_kind!r}, not {kind!r}')
        return parent

    def _canonical(self, row, model, errors):
        spec = row.get("canonical") or {}
        canonical_model = CANONICAL_MODELS.get(spec.get("model"))
        if canonical_model is None:
            errors.append(f'canonical.model must be one of {", ".join(CANONICAL_MODELS)} (got {spec.get("model")!r})')
            return None, ""
        title = spec.get("match_title") or ""
        matches = list(canonical_model.objects.live().filter(title=title))
        if len(matches) != 1:
            errors.append(f'canonical: {len(matches)} live {spec["model"]} page(s) titled exactly {title!r}; need exactly 1')
            return None, ""
        match = matches[0]
        limit = model._meta.get_field("canonical").get_limit_choices_to()
        if limit and not canonical_model.objects.filter(pk=match.pk).complex_filter(limit).exists():
            errors.append(f"canonical: #{match.pk} {match.title!r} isn't an allowed canonical page for {model.__name__}")
        hint = spec.get("production_id_hint")
        if hint is None:
            hint_note = "no production_id_hint"
        elif hint == match.pk:
            hint_note = f"production_id_hint {hint}: matches"
        else:
            hint_note = f"production_id_hint {hint}: differs (expected outside production; IDs aren't used to link)"
        return match, hint_note

    def _desired(self, row, model, errors):
        L = _check_length
        text_fields = {"student_title": "student_title", "subtitle": "subtitle",
                       "think_about_it": "think_about_it", "reflection_question": "reflection_question"}
        if model is SaintLearningPage:
            text_fields["kindness_prompt"] = "kindness_prompt"
        scalars = {}
        for key, field in text_fields.items():
            value = row.get(key) or ""
            if not isinstance(value, str):
                errors.append(f'"{key}" must be text')
                continue
            L(errors, model, field, value, key)
            scalars[field] = value
        L(errors, model, "title", row["student_title"], "student_title (as the page title)")
        L(errors, model, "slug", row["slug"], "slug")
        scalars["title"] = row["student_title"]
        scalars["slug"] = row["slug"]

        # story_label: the saint pages' existing choice (the/his/her); other types always say "The Story".
        label = row.get("story_label") or ""
        if model is SaintLearningPage:
            by_label = {lbl: key for key, lbl in STORY_HEADING_CHOICES}
            keys = {key for key, _ in STORY_HEADING_CHOICES}
            if not label:
                scalars["story_label"] = "the"
            elif label in by_label or label in keys:
                scalars["story_label"] = by_label.get(label, label)
            else:
                errors.append(f'story_label {label!r} must be one of {", ".join(by_label)}')
        elif label and label != "The Story":
            errors.append(f'story_label {label!r}: {model.__name__} has no story label field (it always shows "The Story")')

        if not isinstance(row.get("intro"), str):
            errors.append('"intro" must be text')
        paragraphs = row.get("story_paragraphs")
        if not isinstance(paragraphs, list) or not all(isinstance(p, str) and p.strip() for p in paragraphs):
            errors.append('"story_paragraphs" must be a list of non-empty text paragraphs')
            paragraphs = []
        scalars["intro"] = _paragraphs([row["intro"]]) if isinstance(row.get("intro"), str) else ""
        scalars["story"] = _paragraphs(paragraphs)

        children = {
            "quick_facts": self._quick_facts(row.get("quick_facts") or [], model, errors),
            "timeline": [], "fun_facts": [], "words": [], "sources": [], "quiz": [],
        }
        for i, t in enumerate(row.get("timeline") or []):
            if set(t) - {"date_display", "text"}:
                errors.append(f"timeline[{i}]: unknown key(s) {sorted(set(t) - {'date_display', 'text'})}")
            L(errors, TimelineEntry, "date_display", t.get("date_display", ""), f"timeline[{i}].date_display")
            L(errors, TimelineEntry, "text", t.get("text", ""), f"timeline[{i}].text")
            children["timeline"].append({"date_display": t.get("date_display", ""), "text": t.get("text", "")})
        for i, f in enumerate(row.get("fun_facts") or []):
            if not isinstance(f, str):
                errors.append(f"fun_facts[{i}] must be text")
                continue
            L(errors, FunFact, "text", f, f"fun_facts[{i}]")
            children["fun_facts"].append({"text": f})
        for i, w in enumerate(row.get("words_to_know") or []):
            if set(w) - {"word", "definition"}:
                errors.append(f"words_to_know[{i}]: unknown key(s) {sorted(set(w) - {'word', 'definition'})}")
            L(errors, WordToKnow, "word", w.get("word", ""), f"words_to_know[{i}].word")
            L(errors, WordToKnow, "definition", w.get("definition", ""), f"words_to_know[{i}].definition")
            children["words"].append({"word": w.get("word", ""), "definition": w.get("definition", "")})
        url_ok = URLValidator(schemes=["https"])
        for i, s in enumerate(row.get("sources") or []):
            if set(s) - {"title", "url", "publisher", "note"}:
                errors.append(f"sources[{i}]: unknown key(s) {sorted(set(s) - {'title', 'url', 'publisher', 'note'})}")
            for key in ("title", "url", "publisher", "note"):
                L(errors, SourceLink, key, s.get(key, "") or "", f"sources[{i}].{key}")
            try:
                url_ok(s.get("url", ""))
            except ValidationError:
                errors.append(f"sources[{i}].url must be a valid https URL (got {s.get('url')!r})")
            children["sources"].append({k: s.get(k, "") or "" for k in ("title", "url", "publisher", "note")})

        quiz = row.get("quiz") or []
        if len(quiz) != QUIZ_LENGTH:
            errors.append(f"quiz must have exactly {QUIZ_LENGTH} questions (it has {len(quiz)})")
        for i, q in enumerate(quiz):
            if set(q) - {"prompt", "choices", "explanation"}:
                errors.append(f"quiz[{i}]: unknown key(s) {sorted(set(q) - {'prompt', 'choices', 'explanation'})}")
            L(errors, QuizQuestion, "prompt", q.get("prompt", ""), f"quiz[{i}].prompt")
            L(errors, QuizQuestion, "explanation", q.get("explanation", ""), f"quiz[{i}].explanation")
            choices = q.get("choices") or []
            if not 3 <= len(choices) <= 4:
                errors.append(f"quiz[{i}] needs 3 or 4 choices (it has {len(choices)})")
            correct = sum(1 for c in choices if c.get("correct") is True)
            if correct != 1:
                errors.append(f"quiz[{i}] needs exactly one correct choice (it has {correct})")
            out = []
            for j, c in enumerate(choices):
                if set(c) - {"text", "correct"}:
                    errors.append(f"quiz[{i}].choices[{j}]: unknown key(s) {sorted(set(c) - {'text', 'correct'})}")
                L(errors, QuizChoice, "text", c.get("text", ""), f"quiz[{i}].choices[{j}]")
                out.append({"text": c.get("text", ""), "is_correct": c.get("correct") is True})
            children["quiz"].append({"prompt": q.get("prompt", ""), "explanation": q.get("explanation", ""), "choices": out})

        hits = sorted({m.group(0) for m in GRADE_WORDING.finditer(json.dumps(row, ensure_ascii=False))})
        if hits:
            errors.append(f"grade-level wording isn't allowed (found: {', '.join(hits)})")
        return scalars, children

    def _quick_facts(self, facts, model, errors):
        inherit_map = SAINT_INHERIT if model is SaintLearningPage else SITE_INHERIT
        allowed_keys = set(SAINT_SOURCES if model is SaintLearningPage else SITE_SOURCES)
        icons = {key for key, _ in QuickFact._meta.get_field("icon").choices if key}
        icon_labels = {lbl: key for key, lbl in QuickFact._meta.get_field("icon").choices if key}
        out = []
        for i, f in enumerate(facts):
            where = f"quick_facts[{i}]"
            extra = set(f) - {"icon", "label", "inherit", "fallback_value", "value"}
            if extra:
                errors.append(f"{where}: unknown key(s) {sorted(extra)}")
            icon = ICON_ALIASES.get(f.get("icon", ""), f.get("icon", ""))
            icon = icon_labels.get(icon, icon)
            if icon and icon not in icons:
                errors.append(f"{where}: icon {f.get('icon')!r} isn't one of the model's icons ({', '.join(sorted(icons))})")
            inherit = f.get("inherit") or ""
            if inherit:
                inherit = inherit_map.get(inherit, inherit)
                if inherit not in allowed_keys:
                    errors.append(f"{where}: inherit {f.get('inherit')!r} isn't available for {model.__name__}")
                if "value" in f:
                    errors.append(f'{where}: use "fallback_value" with "inherit", not "value"')
                value = f.get("fallback_value") or ""
            else:
                if "fallback_value" in f:
                    errors.append(f'{where}: "fallback_value" needs "inherit"')
                value = f.get("value") or ""
                if not value:
                    errors.append(f'{where}: needs "value" or "inherit"')
            L = _check_length
            L(errors, QuickFact, "label", f.get("label", ""), f"{where}.label")
            L(errors, QuickFact, "value", value, f"{where}.{'fallback_value' if inherit else 'value'}")
            out.append({"icon": icon, "label": f.get("label", ""), "inherit": inherit, "value": value})
        return out

    # --- reading a page back -------------------------------------------------
    @staticmethod
    def _ordered(items):
        return sorted(items, key=lambda o: (o.sort_order if o.sort_order is not None else 0))

    def represent(self, page, model):
        scalars = {f: getattr(page, f) or "" for f in
                   ("title", "slug", "student_title", "subtitle", "think_about_it", "reflection_question", "intro", "story")}
        if model is SaintLearningPage:
            scalars["kindness_prompt"] = page.kindness_prompt or ""
            scalars["story_label"] = page.story_label or "the"
        scalars["canonical_id"] = page.canonical_id
        children = {
            "quick_facts": [{"icon": q.icon, "label": q.label, "inherit": q.inherit, "value": q.value}
                            for q in self._ordered(page.quick_facts.all())],
            "timeline": [{"date_display": t.date_display, "text": t.text} for t in self._ordered(page.timeline.all())],
            "fun_facts": [{"text": f.text} for f in self._ordered(page.fun_facts.all())],
            "words": [{"word": w.word, "definition": w.definition} for w in self._ordered(page.words.all())],
            "sources": [{"title": s.title, "url": s.url, "publisher": s.publisher, "note": s.note}
                        for s in self._ordered(page.sources.all())],
            "quiz": [{"prompt": q.prompt, "explanation": q.explanation,
                      "choices": [{"text": c.text, "is_correct": c.is_correct} for c in self._ordered(q.choices.all())]}
                     for q in self._ordered(page.quiz_questions.all())],
        }
        return scalars, children

    @staticmethod
    def differences(have, want):
        (hs, hc), (ws, wc) = have, want
        diffs = [f"{k}: differs" for k in ws if hs.get(k) != ws[k]]
        for name, wanted in wc.items():
            got = hc.get(name, [])
            if len(got) != len(wanted):
                diffs.append(f"{name}: {len(got)} item(s), file has {len(wanted)}")
                continue
            diffs += [f"{name}[{i}]: differs" for i, (g, w) in enumerate(zip(got, wanted)) if g != w]
        return diffs

    # --- writing ---------------------------------------------------------------
    def _existing(self, plan):
        sibling = plan["parent"].get_children().filter(slug=plan["scalars"]["slug"]).first()
        if sibling is not None and not isinstance(sibling.specific, plan["model"]):
            raise PageError(f'slug "{plan["scalars"]["slug"]}" is already used by a {type(sibling.specific).__name__}')
        return sibling.specific if sibling is not None else None

    def _fill(self, page, plan):
        for field, value in plan["scalars"].items():
            setattr(page, field, value)
        c = plan["children"]
        page.quick_facts = [QuickFact(sort_order=i, **f) for i, f in enumerate(c["quick_facts"])]
        page.timeline = [TimelineEntry(sort_order=i, **t) for i, t in enumerate(c["timeline"])]
        page.fun_facts = [FunFact(sort_order=i, **f) for i, f in enumerate(c["fun_facts"])]
        page.words = [WordToKnow(sort_order=i, **w) for i, w in enumerate(c["words"])]
        page.sources = [SourceLink(sort_order=i, **s) for i, s in enumerate(c["sources"])]
        questions = []
        for i, q in enumerate(c["quiz"]):
            question = QuizQuestion(sort_order=i, prompt=q["prompt"], explanation=q["explanation"])
            question.choices = [QuizChoice(sort_order=j, **ch) for j, ch in enumerate(q["choices"])]
            questions.append(question)
        page.quiz_questions = questions

    def report(self, plan, action, extra=""):
        p = plan
        c = p["children"]
        self.stdout.write(f"{action}: {p['parent'].url_path}{p['scalars']['slug']}/  ({p['model'].__name__}){extra}")
        self.stdout.write(f"  parent: {p['parent'].url_path} ({p['parent'].title}, content_kind {p['parent'].content_kind})")
        self.stdout.write(f"  canonical: #{p['canonical'].pk} {p['canonical'].title!r}  ({p['hint_note']})")
        self.stdout.write(
            f"  counts: story paragraphs {len(p['row']['story_paragraphs'])}, quick facts {len(c['quick_facts'])}, "
            f"timeline {len(c['timeline'])}, fun facts {len(c['fun_facts'])}, words {len(c['words'])}, "
            f"sources {len(c['sources'])}, quiz {len(c['quiz'])} questions / "
            f"{sum(len(q['choices']) for q in c['quiz'])} choices; intro {p['words'][0]} words, story {p['words'][1]} words"
        )
        for f in c["quick_facts"]:
            if f["inherit"]:
                live = _canonical_value(f["inherit"], p["canonical"])
                shown = f"{live!r} (from the canonical page)" if live else f"{f['value']!r} (fallback_value; canonical field empty)"
                self.stdout.write(f"  quick fact {f['label']!r} inherits {f['inherit']}: shows {shown}")
        for w in p["warnings"]:
            self.stdout.write(self.style.WARNING(f"  warning: {w}"))

    def apply(self, plan, dry_run):
        try:
            existing = self._existing(plan)
        except PageError as exc:
            self.stdout.write(self.style.ERROR(f"FAILED: {exc}"))
            return "failed"
        want = (plan["scalars"], plan["children"])
        if existing is None:
            if not dry_run:
                with transaction.atomic():
                    page = plan["model"](live=False, show_in_menus=False)
                    self._fill(page, plan)
                    plan["parent"].add_child(instance=page)
                    page.save_revision(log_action=True)
            self.report(plan, "Would create (draft)" if dry_run else "Created (draft, unpublished)")
            return "created"

        latest = existing.get_latest_revision_as_object()
        diffs = self.differences(self.represent(latest, plan["model"]), want)
        if not diffs:
            self.report(plan, "Unchanged", "  (0 differences; no revision)")
            return "unchanged"
        if existing.has_unpublished_changes:
            self.report(plan, "Skipped", f"  (it has an unpublished draft; {len(diffs)} difference(s) not imported)")
            return "skipped"
        if not dry_run:
            with transaction.atomic():
                self._fill(latest, plan)
                latest.save_revision(log_action=True)
        self.report(plan, "Would update (new draft revision)" if dry_run else "Updated (new draft revision)",
                    f"  ({len(diffs)} difference(s))")
        return "updated"

    def verify(self, plan):
        try:
            existing = self._existing(plan)
        except PageError as exc:
            self.stdout.write(self.style.ERROR(f"FAILED: {exc}"))
            return 1
        where = f"{plan['parent'].url_path}{plan['scalars']['slug']}/"
        if existing is None:
            self.stdout.write(self.style.ERROR(f"{where}: no such page"))
            return 1
        latest = existing.get_latest_revision_as_object()
        diffs = self.differences(self.represent(latest, plan["model"]), (plan["scalars"], plan["children"]))
        state = "live" if existing.live else "draft (unpublished)"
        self.stdout.write(f"{where}  #{existing.pk} {state}: {len(diffs)} difference(s) in the latest revision")
        for d in diffs:
            self.stdout.write(f"  - {d}")
        return len(diffs)
