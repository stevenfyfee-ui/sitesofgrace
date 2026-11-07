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

        saint = home.saint_of_week
        self.stdout.write(f"Saint of the Week: {saint.title if saint else 'none'} "
                          f"(portrait shown: {'yes' if saint and saint.portrait_id and saint.portrait_credit else 'no, placeholder'})")
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
            student_title="" if model is SaintLearningPage else canonical.title,
            subtitle="[SAMPLE] One italic line about this story goes here.",
            intro=filler(65, 2),
            story=filler(320, 4),
            think_about_it="[SAMPLE] A question to think about goes here?",
            reflection_question="[SAMPLE] A reflection question goes here?",
        )
        if model is SaintLearningPage:
            # The canonical page's own name, so the heading reads "Meet Saint …".
            page.saint_name = canonical.title.removeprefix("St. ").removeprefix("Saint ")
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
