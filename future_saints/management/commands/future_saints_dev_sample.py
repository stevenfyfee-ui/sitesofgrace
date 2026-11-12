"""Local-only sample content for reviewing the Future Saints layouts.

    python manage.py future_saints_dev_sample

Refuses to run unless settings.DEBUG is True and the database is local.
Builds the tree with create_future_saints_tree if it isn't there, fills only
BLANK card lines with "(sample)" placeholder text, picks a live saint for
Saint of the Week by slug (never by page ID), and publishes the six Future
Saints pages locally.

Phase 2: adds one learning page of each type (title ends "(sample)"), each
linked by slug to a LOCAL canonical page. Quick Facts inherit the real
canonical values live. Every prose field is obvious "[SAMPLE TEXT]" filler at
the target lengths (one version for grades 2–5: intro 50–80 words, story
250–400) with no dates, names or claims; quiz items start "[SAMPLE]". No canonical page is
changed. A type whose sample already exists is left alone.
"""
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from catalog.models import SacredSitePage, SaintPage
from future_saints.models import (
    ArchitecturalFeature,
    EucharisticLearningPage,
    FunFact,
    FutureSaintsHomePage,
    FutureSaintsIndexPage,
    GuideBuildStep,
    GuideChecklistItem,
    GuideFactCardLabel,
    GuidePlanStep,
    GuideSafetyItem,
    GuideSupply,
    HolyLandLearningPage,
    HubQuizChoice,
    HubQuizQuestion,
    MarianLearningPage,
    MissionLearningPage,
    MissionProjectsGuidePage,
    MissionSchoolProject,
    ProjectFactCardRow,
    ProjectMaterial,
    ProjectSource,
    ProjectStep,
    QuickFact,
    QuizChoice,
    QuizQuestion,
    SaintLearningPage,
    SourceLink,
    TimelineEntry,
    WordToKnow,
)

LOCAL_DB_HOSTS = {"db", "localhost", "127.0.0.1", ""}

SAINT_OF_WEEK_SLUG = "st-francis-of-assisi"
SAMPLE_LINE = "A short line for children goes here (sample)"
SAMPLE_INTRO = "A short welcome for this subject goes here (sample)"

FILLER = (
    "This sentence holds the place of real story text that an editor will write and a reviewer will check. "
    "It is here only so the page can be judged at its true length. "
    "Nothing in it is a fact about any person, place or event. "
)

# (model, index content_kind, canonical model, canonical slug, quick facts as (icon, label, inherit))
SAMPLES = [
    (SaintLearningPage, "saint", SaintPage, "st-francis-of-assisi", [
        ("calendar", "Lived", "saint_lived"), ("feast", "Feast Day", "saint_feast"),
        ("star", "Canonized", "saint_canonized"), ("chalice", "Known for", ""),
    ]),
    (MarianLearningPage, "marian_apparition", SacredSitePage, "lourdes", [
        ("marker", "Where", "site_place"), ("calendar", "When", "site_date"),
        ("feast", "Feast Day", "site_feast"), ("star", "Church status", "site_status"),
    ]),
    (EucharisticLearningPage, "eucharistic_miracle", SacredSitePage, "eucharistic-miracle-of-lanciano", [
        ("marker", "Where", "site_place"), ("calendar", "When", "site_date"),
        ("feast", "Feast Day", "site_feast"), ("chalice", "Church status", "site_status"),
    ]),
    (HolyLandLearningPage, "holy_land", SacredSitePage, "church-of-the-holy-sepulchre", [
        ("marker", "Where", "site_place"), ("calendar", "When", "site_date"),
        ("scroll", "In the Bible", ""), ("star", "Why it matters", ""),
    ]),
    (MissionLearningPage, "california_mission", SacredSitePage, "mission-san-diego-de-alcala", [
        ("marker", "Where", "site_place"), ("calendar", "Date", "site_date"),
        ("church", "Founding #", ""), ("star", "Named for", ""),
    ]),
]


def refuse_unless_local():
    if not settings.DEBUG:
        raise CommandError("future_saints_dev_sample only runs with DEBUG = True.")
    module = getattr(settings, "SETTINGS_MODULE", "") or ""
    host = connection.settings_dict.get("HOST") or ""
    if module.endswith("production") or host not in LOCAL_DB_HOSTS:
        raise CommandError(f"future_saints_dev_sample refuses to run against this database (host {host!r}).")


def publish(page):
    page.save_revision(log_action=True).publish()


def filler(words, paragraphs=1):
    """About `words` words of [SAMPLE TEXT] filler, split into <p> paragraphs."""
    base = FILLER.split()
    text = (base * (words // len(base) + 1))[:words]
    size = max(1, len(text) // paragraphs)
    chunks = [text[i:i + size] for i in range(0, len(text), size)][:paragraphs]
    return "".join(f"<p>[SAMPLE TEXT] {' '.join(chunk)}</p>" for chunk in chunks)


def sample_line(n=None):
    return f"[SAMPLE] Short line {n} for children." if n else "[SAMPLE] One short line for children."


class Command(BaseCommand):
    help = "Local-only Future Saints sample content (DEBUG and a local database required)."

    def handle(self, *args, **options):
        refuse_unless_local()
        if not FutureSaintsHomePage.objects.exists():
            call_command("create_future_saints_tree", stdout=self.stdout)

        with transaction.atomic():
            home = FutureSaintsHomePage.objects.get()
            for field in ("card_1_line", "card_2_line", "card_3_line", "card_4_line", "holy_land_line"):
                if not getattr(home, field):
                    setattr(home, field, SAMPLE_LINE)
            if home.saint_of_week_id is None:
                saint = (SaintPage.objects.live().filter(slug=SAINT_OF_WEEK_SLUG).first()
                         or SaintPage.objects.live().order_by("title").first())
                home.saint_of_week = saint
                if not home.saint_of_week_line:
                    home.saint_of_week_line = SAMPLE_LINE
            publish(home)
            for index in FutureSaintsIndexPage.objects.child_of(home):
                if not index.intro:
                    index.intro = SAMPLE_INTRO
                publish(index)

            made = [self.learning_sample(home, *row) for row in SAMPLES]
            made += self.phase3_sample(home)

        saint = home.saint_of_week
        self.stdout.write(f"Saint of the Week: {saint.title if saint else 'none'} "
                          "(placeholder frame; the adult portrait is never used)")
        for line in made:
            self.stdout.write(line)
        self.stdout.write(self.style.SUCCESS(
            "Published the Future Saints pages locally. They render only when "
            "SOG_FUTURE_SAINTS allows the request."
        ))

    def learning_sample(self, home, model, kind, canonical_model, slug, facts):
        index = FutureSaintsIndexPage.objects.child_of(home).filter(content_kind=kind).first()
        label = model._meta.verbose_name
        if index is None:
            return f"{label}: no {kind} index, skipped"
        existing = model.objects.child_of(index).first()
        if existing is not None:
            return f"{label}: sample already exists ({existing.url_path}), left alone"
        canonical = canonical_model.objects.live().filter(slug=slug).first()
        if canonical is None:
            return f"{label}: no live local canonical page with slug {slug!r}, skipped"

        page = model(
            title=f"{canonical.title} (sample)",
            slug=f"{slug}-sample",
            canonical=canonical,
            student_title=canonical.title,
            subtitle="[SAMPLE] One italic line about this story goes here.",
            intro=filler(65, 2),
            story=filler(320, 4),
            think_about_it="[SAMPLE] A question to think about goes here?",
            reflection_question="[SAMPLE] A reflection question goes here?",
        )
        if model is SaintLearningPage:
            page.story_label = "his"
            page.virtues = "[SAMPLE] virtue one, virtue two"
            page.kindness_prompt = "[SAMPLE] A small act of kindness to try goes here."
        elif model is MarianLearningPage:
            page.witnesses = filler(45)
            page.message = filler(40)
            page.prayer = filler(35)
            page.recognition_note = filler(40)
        elif model is EucharisticLearningPage:
            page.belief = filler(50)
            page.reported = filler(45)
            page.church_says = filler(45)
            page.evidence_note = filler(35)
        elif model is HolyLandLearningPage:
            page.people_places = filler(60)
            page.then_and_now = filler(50)
            page.what_we_know = filler(40)
            page.tradition = filler(40)
        elif model is MissionLearningPage:
            page.native_peoples = filler(120, 2)
            page.mission_life = filler(80)
            page.architecture = filler(50)

        page.quick_facts = [
            QuickFact(sort_order=i, icon=icon, label=fact_label, inherit=inherit, value="" if inherit else "[SAMPLE] value")
            for i, (icon, fact_label, inherit) in enumerate(facts)
        ]
        page.timeline = [
            TimelineEntry(sort_order=n, date_display="[SAMPLE]", text=sample_line(n))
            for n in range(1, 5)
        ]
        page.fun_facts = [FunFact(sort_order=n, text=f"[SAMPLE] Fun fact {n} goes here.") for n in range(1, 5)]
        page.words = [
            WordToKnow(sort_order=n, word=f"[SAMPLE] word {n}", definition=f"[SAMPLE] A simple meaning for word {n}.")
            for n in range(1, 5)
        ]
        page.sources = [
            SourceLink(sort_order=n, title=f"[SAMPLE] Source {n} title", publisher="[SAMPLE] Publisher", note="[SAMPLE] What this source supports.")
            for n in range(1, 3)
        ]
        questions = []
        for n in range(1, 6):
            q = QuizQuestion(sort_order=n, prompt=f"[SAMPLE] Question {n} goes here?", explanation=f"[SAMPLE] A kind explanation of answer {n}.")
            q.choices = [QuizChoice(sort_order=i, text=f"[SAMPLE] Choice {letter}", is_correct=(letter == "B"))
                         for i, letter in enumerate("ABCD")]
            questions.append(q)
        page.quiz_questions = questions

        index.add_child(instance=page)
        publish(page)
        return f"{label}: created {page.url_path} from local canonical {slug!r}"

    def phase3_sample(self, home):
        """Phase 3: the hub's text and quiz (only where blank), the projects guide, and a
        published Build This Mission project on the mission sample. All "[SAMPLE]" filler.
        The 21 map missions come from seed_mission_hub, not from here."""
        hub = FutureSaintsIndexPage.objects.child_of(home).filter(content_kind="california_mission").first()
        if hub is None:
            return ["Missions hub: no california_mission index, skipped"]
        lines = []
        hub = hub.get_latest_revision_as_object() if hub.get_latest_revision() else hub
        for field, value in {
            "hub_eyebrow": "California Missions", "hub_title": "[SAMPLE] Discover the California Missions",
            "hub_subtitle": "[SAMPLE] One italic line about the missions goes here.",
            "hub_intro": "[SAMPLE TEXT] " + FILLER, "map_note": "[SAMPLE] A short note about the founding numbers goes here.",
            "timeline_heading": "The Missions in Founding Order", "native_peoples_text": "[SAMPLE TEXT] " + FILLER * 2,
            "projects_banner_heading": "[SAMPLE] Building a mission model for school?",
            "projects_banner_text": "[SAMPLE] One line about the project guide goes here.", "projects_banner_button": "See Mission Projects",
        }.items():
            if not getattr(hub, field):
                setattr(hub, field, value)
        if not hub.hub_quiz_questions.exists():
            questions = []
            for n in range(1, 6):
                q = HubQuizQuestion(sort_order=n, prompt=f"[SAMPLE] Hub question {n} goes here?", explanation="[SAMPLE] A kind explanation.")
                q.choices = [HubQuizChoice(sort_order=i, text=f"[SAMPLE] Choice {letter}", is_correct=(letter == "C"))
                             for i, letter in enumerate("ABCD")]
                questions.append(q)
            hub.hub_quiz_questions = questions
        publish(hub)
        lines.append(f"Missions hub: sample text and quiz where blank, published {hub.url_path}")

        if not MissionProjectsGuidePage.objects.child_of(hub).exists():
            guide = MissionProjectsGuidePage(
                title="How to Build a California Mission Model (sample)", slug="projects",
                intro="[SAMPLE TEXT] " + FILLER, supplies_note="[SAMPLE] A note about asking a grown-up goes here.",
                remember_people="[SAMPLE TEXT] " + FILLER,
            )
            guide.plan_steps = [GuidePlanStep(sort_order=n, title=f"[SAMPLE] Plan step {n}.", text=sample_line(n)) for n in range(1, 6)]
            guide.supplies = [GuideSupply(sort_order=n, text=f"[SAMPLE] Supply {n}") for n in range(1, 8)]
            guide.safety_items = [GuideSafetyItem(sort_order=n, lead="[SAMPLE]" if n == 1 else "", text=sample_line(n)) for n in range(1, 5)]
            guide.build_steps = [GuideBuildStep(sort_order=n, title=f"[SAMPLE] Build step {n}.", text=sample_line(n)) for n in range(1, 9)]
            guide.fact_card_labels = [GuideFactCardLabel(sort_order=n, label=label) for n, label in
                                      enumerate(["Mission name", "Founding #", "Year founded", "Founded by", "My name"])]
            guide.checklist_items = [GuideChecklistItem(sort_order=n, text=f"[SAMPLE] Checklist item {n}") for n in range(1, 8)]
            hub.add_child(instance=guide)
            publish(guide)
            lines.append(f"Projects guide: created {guide.url_path}")

        mission = MissionLearningPage.objects.child_of(hub).filter(slug__endswith="-sample").first()
        if mission is None or mission.school_projects.exists():
            lines.append("Build This Mission sample: no mission sample page, or it already has a project; left alone")
            return lines
        project = MissionSchoolProject(
            page=mission, project_title="[SAMPLE] Build This Mission", status="published",
            grade_note="[SAMPLE] Who this is good for", difficulty="[SAMPLE] Beginner", stages_summary="[SAMPLE] Plan → Base → Build → Paint",
            project_intro="[SAMPLE TEXT] " + FILLER, model_reference_image=sample_image(),
            model_reference_image_alt="[SAMPLE] A plain placeholder picture", historical_vs_restored_note="[SAMPLE TEXT] " + FILLER,
            finishing_tips="[SAMPLE TEXT] " + FILLER, adult_supervision_notes="[SAMPLE] A grown-up does all cutting.",
        )
        project.features = [ArchitecturalFeature(sort_order=n, title=f"[SAMPLE] Feature {n}", text=sample_line(n)) for n in range(1, 4)]
        project.materials = [ProjectMaterial(sort_order=n, item=f"[SAMPLE] Material {n}", quantity="1",
                                             alternative="[SAMPLE] Something else", safety_note="") for n in range(1, 7)]
        project.steps = [ProjectStep(sort_order=n, title=f"[SAMPLE] Step {n}", instructions=FILLER) for n in range(1, 9)]
        project.fact_card_rows = [ProjectFactCardRow(sort_order=n, label=label, value="[SAMPLE]") for n, label in
                                  enumerate(["Mission", "Founding #", "Founded", "Founded by", "Named for", "Native people"])]
        project.sources = [ProjectSource(sort_order=n, title=f"[SAMPLE] Source {n} title", publisher="[SAMPLE] Publisher") for n in range(1, 3)]
        project.save()
        lines.append(f"Build This Mission sample: published on {mission.url_path}")
        return lines


def sample_image():
    """A plain parchment-coloured placeholder picture, clearly titled as a sample."""
    from io import BytesIO

    from django.core.files.images import ImageFile
    from PIL import Image
    from wagtail.images import get_image_model

    buffer = BytesIO()
    Image.new("RGB", (1600, 900), (233, 220, 190)).save(buffer, format="PNG")
    return get_image_model().objects.create(title="[SAMPLE] Placeholder picture",
                                            file=ImageFile(buffer, name="future-saints-sample.png"))
