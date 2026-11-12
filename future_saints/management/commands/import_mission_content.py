"""Import the approved California Missions content (Phase 3, step 6) as drafts.

    python manage.py import_mission_content --dry-run
    python manage.py import_mission_content
    python manage.py import_mission_content --verify

Format "future-saints-missions-content/v1" (docs/future-saints/content/missions-hub-and-projects.json,
converted from the approved Markdown with no wording changes). Three parts:

- "hub": the California Missions index's hub text and its five-question quiz.
- "guide": the projects guide page at <hub>/projects/ (created unpublished if missing).
- "project": Build This Mission on the mission learning page whose canonical page is the one
  live catalog.SacredSitePage titled exactly "mission.match_title".

Each part is saved as a new DRAFT revision built on the page's latest revision, so the
seeded hub missions (or any other draft work on those pages) are kept: only the fields this
file owns are replaced (the hub's text and quiz; the guide's content; the mission page's
project). It never publishes and never submits to the workflow. Everything is validated
before anything is written (lengths from the models, rejected never truncated; the quiz's
5 questions with 3-4 choices and one correct; https URLs; no grade-level wording; no
shopping words), --dry-run and --verify write nothing, and a second run reports 0 changed.
"""
import json
import re

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator
from django.db import transaction

from catalog.models import SacredSitePage
from future_saints.management.commands.import_learning_pages import GRADE_WORDING, _check_length
from future_saints.missions import PROJECT_STATUS_CHOICES
from future_saints.models import (
    ArchitecturalFeature,
    FutureSaintsIndexPage,
    GuideBuildStep,
    GuideChecklistItem,
    GuideFactCardLabel,
    GuidePlanStep,
    GuideSafetyItem,
    GuideSupply,
    HubQuizChoice,
    HubQuizQuestion,
    MissionLearningPage,
    MissionProjectsGuidePage,
    MissionSchoolProject,
    ProjectFactCardRow,
    ProjectMaterial,
    ProjectSource,
    ProjectStep,
)

FORMAT = "future-saints-missions-content/v1"
DEFAULT_PATH = "docs/future-saints/content/missions-hub-and-projects.json"
QUIZ_LENGTH = 5
SHOPPING = re.compile(r"\b(buy|shop|store|price|amazon|amzn|affiliate)\b", re.IGNORECASE)
TOP_KEYS = {"format", "source", "approved_by", "approved_on", "hub", "guide", "project"}
HUB_FIELDS = {
    "eyebrow": "hub_eyebrow", "title": "hub_title", "subtitle": "hub_subtitle", "intro": "hub_intro",
    "map_note": "map_note", "native_peoples_text": "native_peoples_text", "timeline_heading": "timeline_heading",
    "projects_banner_heading": "projects_banner_heading", "projects_banner_text": "projects_banner_text",
    "projects_banner_button": "projects_banner_button",
}
GUIDE_FIELDS = {"title": "title", "slug": "slug", "intro": "intro", "supplies_note": "supplies_note", "remember_people": "remember_people"}
GUIDE_LISTS = {
    # json key: (relation, model, {json key: model field}) -- a plain string becomes the first field
    "plan_steps": ("plan_steps", GuidePlanStep, {"title": "title", "text": "text"}),
    "supplies": ("supplies", GuideSupply, {"text": "text"}),
    "safety_items": ("safety_items", GuideSafetyItem, {"lead": "lead", "text": "text"}),
    "build_steps": ("build_steps", GuideBuildStep, {"title": "title", "text": "text"}),
    "fact_card_labels": ("fact_card_labels", GuideFactCardLabel, {"label": "label"}),
    "checklist_items": ("checklist_items", GuideChecklistItem, {"text": "text"}),
}
PROJECT_FIELDS = ("project_title", "status", "grade_note", "difficulty", "stages_summary", "project_intro",
                  "historical_vs_restored_note", "adult_supervision_notes", "finishing_tips")
PROJECT_LISTS = {
    "features": ("features", ArchitecturalFeature, {"title": "title", "text": "text"}),
    "materials": ("materials", ProjectMaterial, {"item": "item", "quantity": "quantity", "alternative": "alternative", "safety_note": "safety_note"}),
    "steps": ("steps", ProjectStep, {"title": "title", "instructions": "instructions"}),
    "fact_card_rows": ("fact_card_rows", ProjectFactCardRow, {"label": "label", "value": "value"}),
    "sources": ("sources", ProjectSource, {"title": "title", "url": "url", "publisher": "publisher", "note": "note"}),
}


class Command(BaseCommand):
    help = "Import the approved California Missions hub, guide and San Diego project content as drafts."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=DEFAULT_PATH)
        parser.add_argument("--dry-run", action="store_true", help="Validate and report; write nothing.")
        parser.add_argument("--verify", action="store_true", help="Compare the latest revisions with the file; write nothing.")

    # --- entry -------------------------------------------------------------------
    def handle(self, *args, **options):
        if options["dry_run"] and options["verify"]:
            raise CommandError("Use --dry-run or --verify, not both.")
        with open(options["path"], encoding="utf-8") as fh:
            data = json.load(fh)
        errors = []
        plan = self.plan(data, errors)
        mode = "VERIFY" if options["verify"] else ("DRY RUN" if options["dry_run"] else "IMPORT")
        self.stdout.write(f"{mode}: {options['path']} (approved by {data.get('approved_by', '?')} on "
                          f"{data.get('approved_on', '?')}). Nothing is published.")
        if errors:
            for e in errors:
                self.stdout.write(self.style.ERROR(f"  - {e}"))
            raise CommandError(f"{len(errors)} problem(s); nothing was written.")

        totals = {"created": 0, "updated": 0, "unchanged": 0, "differences": 0}
        for part in ("hub", "guide", "project"):
            have = self.represent(part, plan)
            want = plan[part]["want"]
            diffs = differences(have, want)
            self.report(part, plan, diffs)
            if options["verify"]:
                totals["differences"] += len(diffs)
                for d in diffs:
                    self.stdout.write(f"    - {d}")
                continue
            if not diffs:
                totals["unchanged"] += 1
                continue
            totals["created" if have is None else "updated"] += 1
            if not options["dry_run"]:
                with transaction.atomic():
                    self.write(part, plan)
        if options["verify"]:
            if totals["differences"]:
                raise CommandError(f"Verify: {totals['differences']} difference(s).")
            self.stdout.write(self.style.SUCCESS("Verify: 0 differences."))
            return
        changed = totals["created"] + totals["updated"]
        self.stdout.write(f"{'Would change' if options['dry_run'] else 'Changed'}: {changed} "
                          f"(created {totals['created']}, new draft revisions {totals['updated']}); "
                          f"unchanged {totals['unchanged']}.")

    # --- validation --------------------------------------------------------------
    def plan(self, data, errors):
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise CommandError(f'"format" must be "{FORMAT}".')
        unknown = set(data) - TOP_KEYS
        if unknown:
            errors.append(f"unknown key(s): {', '.join(sorted(unknown))}")
        hubs = list(FutureSaintsIndexPage.objects.filter(content_kind="california_mission"))
        if len(hubs) != 1:
            raise CommandError(f"need exactly one California Missions index (found {len(hubs)})")
        hub = hubs[0]
        plan = {"hub": {"page": hub}, "guide": {}, "project": {}}

        h = data.get("hub") or {}
        self.keys(errors, "hub", h, set(HUB_FIELDS) | {"quiz"})
        want = {"fields": {}, "quiz": []}
        for key, field in HUB_FIELDS.items():
            want["fields"][field] = self.text(errors, f"hub.{key}", h.get(key, ""), FutureSaintsIndexPage, field)
        quiz = h.get("quiz") or []
        if len(quiz) != QUIZ_LENGTH:
            errors.append(f"hub.quiz must have exactly {QUIZ_LENGTH} questions (it has {len(quiz)})")
        for i, q in enumerate(quiz):
            self.keys(errors, f"hub.quiz[{i}]", q, {"prompt", "choices", "explanation"})
            choices = q.get("choices") or []
            if not 3 <= len(choices) <= 4:
                errors.append(f"hub.quiz[{i}] needs 3 or 4 choices (it has {len(choices)})")
            correct = sum(1 for c in choices if c.get("correct") is True)
            if correct != 1:
                errors.append(f"hub.quiz[{i}] needs exactly one correct choice (it has {correct})")
            out = []
            for j, c in enumerate(choices):
                self.keys(errors, f"hub.quiz[{i}].choices[{j}]", c, {"text", "correct"})
                out.append({"text": self.text(errors, f"hub.quiz[{i}].choices[{j}]", c.get("text", ""), HubQuizChoice, "text"),
                            "is_correct": c.get("correct") is True})
            want["quiz"].append({
                "prompt": self.text(errors, f"hub.quiz[{i}].prompt", q.get("prompt", ""), HubQuizQuestion, "prompt"),
                "explanation": self.text(errors, f"hub.quiz[{i}].explanation", q.get("explanation", ""), HubQuizQuestion, "explanation"),
                "choices": out})
        plan["hub"]["want"] = want

        g = data.get("guide") or {}
        self.keys(errors, "guide", g, set(GUIDE_FIELDS) | set(GUIDE_LISTS))
        want = {"fields": {f: self.text(errors, f"guide.{k}", g.get(k, ""), MissionProjectsGuidePage, f)
                           for k, f in GUIDE_FIELDS.items()}}
        want["lists"] = self.lists(errors, "guide", g, GUIDE_LISTS)
        plan["guide"] = {"want": want, "page": MissionProjectsGuidePage.objects.child_of(hub).first()}

        p = data.get("project") or {}
        self.keys(errors, "project", p, set(PROJECT_FIELDS) | set(PROJECT_LISTS) | {"mission"})
        mission = p.get("mission") or {}
        title = mission.get("match_title", "")
        if mission.get("model") != "catalog.SacredSitePage":
            errors.append('project.mission.model must be "catalog.SacredSitePage"')
        sites = list(SacredSitePage.objects.live().filter(title=title))
        page = None
        if len(sites) != 1:
            errors.append(f"project.mission: {len(sites)} live page(s) titled exactly {title!r}; need exactly 1")
        else:
            pages = list(MissionLearningPage.objects.child_of(hub).filter(canonical=sites[0]))
            if len(pages) != 1:
                errors.append(f"project.mission: {len(pages)} mission learning page(s) for #{sites[0].pk} {title!r}; need exactly 1")
            else:
                page = pages[0]
        statuses = {k for k, _ in PROJECT_STATUS_CHOICES}
        if p.get("status") not in statuses:
            errors.append(f"project.status must be one of {', '.join(sorted(statuses))}")
        if p.get("status") == "published":
            errors.append('project.status "published" isn\'t imported: an editor publishes a project in the admin')
        want = {"fields": {f: self.text(errors, f"project.{f}", p.get(f, ""), MissionSchoolProject, f) for f in PROJECT_FIELDS}}
        want["lists"] = self.lists(errors, "project", p, PROJECT_LISTS)
        plan["project"] = {"want": want, "page": page, "site": sites[0] if len(sites) == 1 else None}

        url_ok = URLValidator(schemes=["https"])
        for i, s in enumerate(want["lists"]["sources"]):
            try:
                url_ok(s["url"])
            except ValidationError:
                errors.append(f"project.sources[{i}].url must be a valid https URL (got {s['url']!r})")
        blob = json.dumps({k: data.get(k) for k in ("hub", "guide", "project")}, ensure_ascii=False)
        for name, pattern in (("grade-level wording", GRADE_WORDING), ("shopping wording", SHOPPING)):
            hits = sorted({m.group(0) for m in pattern.finditer(blob)})
            if hits:
                errors.append(f"{name} isn't allowed (found: {', '.join(hits)})")
        return plan

    @staticmethod
    def keys(errors, where, obj, allowed):
        if not isinstance(obj, dict):
            errors.append(f"{where} must be an object")
            return
        unknown = set(obj) - allowed
        if unknown:
            errors.append(f"{where}: unknown key(s) {', '.join(sorted(unknown))} (not imported; nothing is dropped silently)")

    @staticmethod
    def text(errors, where, value, model, field):
        if not isinstance(value, str):
            errors.append(f"{where} must be text")
            return ""
        _check_length(errors, model, field, value, where)
        return value

    def lists(self, errors, where, obj, spec):
        out = {}
        for key, (_, model, fields) in spec.items():
            rows = []
            for i, item in enumerate(obj.get(key) or []):
                if isinstance(item, str):
                    item = {next(iter(fields)): item}
                self.keys(errors, f"{where}.{key}[{i}]", item, set(fields))
                rows.append({f: self.text(errors, f"{where}.{key}[{i}].{k}", item.get(k, ""), model, f) for k, f in fields.items()})
            out[key] = rows
        return out

    # --- reading back ------------------------------------------------------------------
    @staticmethod
    def latest(page):
        return page.get_latest_revision_as_object() if page.get_latest_revision() else page

    def represent(self, part, plan):
        page = plan[part]["page"]
        if page is None:
            return None
        page = self.latest(page)
        if part == "hub":
            return {"fields": {f: getattr(page, f) or "" for f in HUB_FIELDS.values()},
                    "quiz": [{"prompt": q.prompt, "explanation": q.explanation,
                              "choices": [{"text": c.text, "is_correct": c.is_correct} for c in ordered(q.choices.all())]}
                             for q in ordered(page.hub_quiz_questions.all())]}
        if part == "guide":
            return {"fields": {f: getattr(page, f) or "" for f in GUIDE_FIELDS.values()},
                    "lists": {k: [{f: getattr(o, f) or "" for f in fields.values()} for o in ordered(getattr(page, rel).all())]
                              for k, (rel, _, fields) in GUIDE_LISTS.items()}}
        project = next(iter(page.school_projects.all()), None)
        if project is None:
            return {"fields": {}, "lists": {}}
        return {"fields": {f: getattr(project, f) or "" for f in PROJECT_FIELDS},
                "lists": {k: [{f: getattr(o, f) or "" for f in fields.values()} for o in ordered(getattr(project, rel).all())]
                          for k, (rel, _, fields) in PROJECT_LISTS.items()}}

    def report(self, part, plan, diffs):
        p = plan[part]
        want = p["want"]
        page = p["page"]
        if part == "hub":
            where = f"{page.url_path} (#{page.pk}, index)"
            counts = f"{sum(1 for v in want['fields'].values() if v)} text fields, quiz {len(want['quiz'])} questions / " \
                     f"{sum(len(q['choices']) for q in want['quiz'])} choices"
        elif part == "guide":
            where = f"{page.url_path} (#{page.pk})" if page else f"{plan['hub']['page'].url_path}{want['fields']['slug']}/ (new, unpublished)"
            counts = ", ".join(f"{k.replace('_', ' ')} {len(v)}" for k, v in want["lists"].items())
        else:
            site = p["site"]
            where = (f"{page.url_path} (#{page.pk}, {'live' if page.live else 'draft'}; canonical #{site.pk} {site.title!r})"
                     if page else "?")
            counts = f"status {want['fields']['status']}; " + ", ".join(f"{k.replace('_', ' ')} {len(v)}" for k, v in want["lists"].items())
        state = "unchanged" if not diffs else ("would create" if self.represent(part, plan) is None else f"{len(diffs)} difference(s)")
        self.stdout.write(f"{part}: {where}: {state}")
        self.stdout.write(f"  {counts}")

    # --- writing -----------------------------------------------------------------
    def write(self, part, plan):
        want = plan[part]["want"]
        if part == "hub":
            page = self.latest(plan["hub"]["page"])
            for field, value in want["fields"].items():
                setattr(page, field, value)
            questions = []
            for i, q in enumerate(want["quiz"]):
                question = HubQuizQuestion(sort_order=i, prompt=q["prompt"], explanation=q["explanation"])
                question.choices = [HubQuizChoice(sort_order=j, **c) for j, c in enumerate(q["choices"])]
                questions.append(question)
            page.hub_quiz_questions = questions
            page.save_revision(log_action=True)
        elif part == "guide":
            existing = plan["guide"]["page"]
            page = self.latest(existing) if existing else MissionProjectsGuidePage(live=False, show_in_menus=False)
            for field, value in want["fields"].items():
                setattr(page, field, value)
            for key, (rel, model, _) in GUIDE_LISTS.items():
                setattr(page, rel, [model(sort_order=i, **row) for i, row in enumerate(want["lists"][key])])
            if existing is None:
                plan["hub"]["page"].add_child(instance=page)
            page.save_revision(log_action=True)
        else:
            page = self.latest(plan["project"]["page"])
            project = MissionSchoolProject(**want["fields"])
            for key, (rel, model, _) in PROJECT_LISTS.items():
                setattr(project, rel, [model(sort_order=i, **row) for i, row in enumerate(want["lists"][key])])
            page.school_projects = [project]
            page.save_revision(log_action=True)


def ordered(items):
    return sorted(items, key=lambda o: o.sort_order if o.sort_order is not None else 0)


def differences(have, want):
    if have is None:
        return ["(missing)"]
    diffs = [f"{name}: differs" for name, value in want["fields"].items() if have["fields"].get(name, "") != value]
    for key in ("quiz",):
        if key in want and have.get(key) != want[key]:
            diffs.append(f"{key}: differs")
    for name, rows in want.get("lists", {}).items():
        got = have.get("lists", {}).get(name, [])
        if got != rows:
            diffs.append(f"{name}: {len(got)} item(s) differ from the file's {len(rows)}" if len(got) != len(rows) else f"{name}: differs")
    return diffs
