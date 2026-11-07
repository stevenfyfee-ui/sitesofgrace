"""Future Saints Phase 2: the five learning (profile) page types.

One shared base, LearningPage, and five sibling types that each add a typed
link to their canonical catalog page plus the brief §4 type-specific fields.
LearningPage is concrete (not abstract) only because the repeating items
(Quick Facts, Timeline, Fun Facts, Words to Know, Sources, Quiz) need a real
model to hang their ParentalKey on; it is never created directly.

Canonical facts (dates, feast day, place, Church status) are read live from
the canonical page through QuickFact.inherit -- never copied into a field.
The canonical page's prose, travel fields and images are never rendered:
Future Saints shows only its own illustrations, and only with a credit.
"""
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.admin.forms import WagtailAdminPageForm
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.fields import RichTextField
from wagtail.models import Orderable, Page

from catalog.models import CANONICAL_STATUS_LABELS

# Imported at the end of future_saints/models.py, after the gate mixin exists.
from .models import FutureSaintsGateMixin

STORY_FEATURES = ["bold", "italic", "ol", "ul", "link"]
SHORT_FEATURES = ["bold", "italic", "link"]

READING_LEVELS = ("explorer", "researcher")
QUIZ_LENGTH = 5
MISSION_TRAIL_SLUG = "california-mission-trail"

QUICK_FACT_ICONS = [
    ("calendar", "Calendar"),
    ("marker", "Place marker"),
    ("feast", "Feast day (calendar with cross)"),
    ("star", "Star"),
    ("chalice", "Chalice"),
    ("church", "Church / mission"),
    ("dove", "Dove"),
    ("scroll", "Scroll"),
    ("book", "Book"),
]

# Canonical fields a Quick Fact may read live. Saint sources apply to saint
# pages, site sources to the other four types.
SAINT_SOURCES = {
    "saint_lived": "Lived (born – died)",
    "saint_born": "Born",
    "saint_died": "Died",
    "saint_feast": "Feast day",
    "saint_canonized": "Canonized",
    "saint_patronage": "Patronage",
    "saint_order": "Religious order",
    "saint_burial": "Burial place",
}
SITE_SOURCES = {
    "site_place": "Place (locality, country)",
    "site_country": "Country",
    "site_date": "Date",
    "site_feast": "Feast day",
    "site_status": "Church status (plain-English label)",
    "site_recognition_year": "Year of the Church's judgment",
}
INHERIT_CHOICES = [("", "Don't inherit: use the value below")] + [
    (key, f"Canonical: {label}") for key, label in {**SAINT_SOURCES, **SITE_SOURCES}.items()
]

STORY_HEADING_CHOICES = [("the", "The Story"), ("his", "His Story"), ("her", "Her Story")]

# The sprite icon drawn in each type's placeholder art frames.
TYPE_ICONS = {
    "saint": "saint",
    "marian_apparition": "mary",
    "eucharistic_miracle": "miracle",
    "holy_land": "holyland",
    "california_mission": "mission",
}


def _image_field(help_text="Shown only when the credit is filled."):
    return models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", help_text=help_text,
    )


def _art(image, alt, credit):
    if image is None or not (credit or "").strip():
        return None
    return {"image": image, "alt": alt or "", "credit": credit.strip()}


def _text(value):
    return str(value or "").strip()


def _canonical_value(source, canonical):
    """The live canonical value behind a Quick Fact, or "" (row hidden)."""
    if canonical is None or not canonical.live:
        return ""
    if source == "saint_lived":
        born, died = _text(canonical.born), _text(canonical.died)
        return f"{born} – {died}" if born and died else born or died
    simple = {
        "saint_born": "born", "saint_died": "died", "saint_feast": "feast_day",
        "saint_canonized": "canonized", "saint_patronage": "patronage",
        "saint_order": "religious_order", "saint_burial": "burial_place",
        "site_country": "country", "site_date": "date_display", "site_feast": "feast_day",
    }
    if source in simple:
        return _text(getattr(canonical, simple[source], ""))
    if source == "site_place":
        return ", ".join(v for v in (_text(canonical.locality), _text(canonical.country)) if v)
    if source == "site_status":
        status = _text(canonical.canonical_status)
        if not status or status == "Not Applicable":
            return ""
        return CANONICAL_STATUS_LABELS.get(status, status)
    if source == "site_recognition_year":
        return str(canonical.recognition_year or "")
    return ""


def _filled(*values):
    return all(_text(v) for v in values)


def _kept_forms(formset):
    """The formset's forms that were cleaned and aren't marked for deletion."""
    if formset is None:
        return []
    return [f for f in formset.forms if hasattr(f, "cleaned_data") and not f.cleaned_data.get("DELETE")]


class LearningPageForm(WagtailAdminPageForm):
    """Quiz rules: every question needs 3–4 choices with exactly one correct
    (checked on every save); publishing also needs exactly five questions.
    Quick Facts may only inherit canonical fields that fit the page type.

    These run in is_valid(), not clean(): a cluster form validates its inline
    formsets after its own clean(), so only then do the question, choice and
    fact rows have cleaned_data to check."""

    def is_valid(self):
        valid = super().is_valid()
        return self._check_quiz() & self._check_quick_facts() & valid

    def _check_quiz(self):
        ok = True
        questions = [f for f in _kept_forms(self.formsets.get("quiz_questions")) if f.cleaned_data.get("prompt")]
        for form in questions:
            choices = [f for f in _kept_forms(form.formsets.get("choices")) if f.cleaned_data.get("text")]
            correct = sum(1 for f in choices if f.cleaned_data.get("is_correct"))
            if not 3 <= len(choices) <= 4:
                form.add_error("prompt", f"A question needs 3 or 4 choices (it has {len(choices)}).")
                ok = False
            if correct != 1:
                form.add_error("prompt", f"Mark exactly one choice correct (it has {correct}).")
                ok = False
        if "action-publish" in self.data and len(questions) != QUIZ_LENGTH:
            self.add_error(None, (
                f"A learning page is published with exactly {QUIZ_LENGTH} quiz questions "
                f"(this one has {len(questions)}). Save a draft until the quiz is complete."
            ))
            ok = False
        return ok

    def _check_quick_facts(self):
        ok = True
        allowed = set(self.instance.quick_fact_sources()) if hasattr(self.instance, "quick_fact_sources") else set()
        for form in _kept_forms(self.formsets.get("quick_facts")):
            inherit = form.cleaned_data.get("inherit")
            if inherit and inherit not in allowed:
                form.add_error("inherit", "That canonical field doesn't belong to this page type.")
                ok = False
            if not inherit and form.cleaned_data.get("label") and not form.cleaned_data.get("value"):
                form.add_error("value", "Give a value, or choose a canonical field to inherit.")
                ok = False
        return ok


class LearningPage(FutureSaintsGateMixin, Page):
    """Shared fields for the five learning types (brief §4). Never created directly."""

    student_title = models.CharField(
        max_length=120, blank=True,
        help_text='The big title, e.g. "Our Lady of Lourdes". Saint pages build "Meet Saint {name}" instead.',
    )
    subtitle = models.CharField(max_length=200, blank=True, help_text="One italic line under the title.")
    hero_illustration = _image_field()
    hero_illustration_alt = models.CharField(max_length=200, blank=True)
    hero_illustration_credit = models.CharField(max_length=255, blank=True)
    context_illustration = _image_field("The small scene behind Quick Facts. Shown only when the credit is filled.")
    context_illustration_alt = models.CharField(max_length=200, blank=True)
    context_illustration_credit = models.CharField(max_length=255, blank=True)
    index_thumbnail = _image_field("The picture on this page's card in its index. Shown only with a credit.")
    index_thumbnail_alt = models.CharField(max_length=200, blank=True)
    index_thumbnail_credit = models.CharField(max_length=255, blank=True)

    explorer_intro = RichTextField(blank=True, features=STORY_FEATURES, help_text="Grades 2–3: the short story beside Quick Facts.")
    researcher_intro = RichTextField(blank=True, features=STORY_FEATURES, help_text="Grades 4–5: the short story beside Quick Facts.")
    explorer_story = RichTextField(blank=True, features=STORY_FEATURES, help_text="Grades 2–3: about 150–250 words.")
    researcher_story = RichTextField(blank=True, features=STORY_FEATURES, help_text="Grades 4–5: about 300–500 words.")
    think_about_it = models.CharField(max_length=200, blank=True, help_text="The question in the Think About It band.")
    reflection_question = models.CharField(max_length=255, blank=True, help_text="Closes the page and the research sheet.")

    show_on_homepage = models.BooleanField(default=False)
    featured_sort_order = models.PositiveSmallIntegerField(null=True, blank=True)
    last_source_reviewed_at = models.DateField(null=True, blank=True)

    parent_page_types = ["future_saints.FutureSaintsIndexPage"]
    subpage_types = []
    is_creatable = False
    base_form_class = LearningPageForm

    # Set on each concrete type.
    content_kind = ""
    canonical_field = "canonical"
    story_sections = ()
    learning_cards = ()

    common_panels = [
        MultiFieldPanel(
            [FieldPanel("student_title"), FieldPanel("subtitle")],
            heading="Title",
        ),
        MultiFieldPanel(
            [
                FieldPanel("hero_illustration"), FieldPanel("hero_illustration_alt"), FieldPanel("hero_illustration_credit"),
                FieldPanel("context_illustration"), FieldPanel("context_illustration_alt"), FieldPanel("context_illustration_credit"),
                FieldPanel("index_thumbnail"), FieldPanel("index_thumbnail_alt"), FieldPanel("index_thumbnail_credit"),
            ],
            heading="Pictures (each shows only when its credit is filled)",
        ),
        MultiFieldPanel(
            [
                FieldPanel("explorer_intro"), FieldPanel("researcher_intro"),
                FieldPanel("explorer_story"), FieldPanel("researcher_story"),
            ],
            heading="Story at two reading levels",
        ),
        InlinePanel("quick_facts", label="Quick Fact", heading="Quick Facts"),
        InlinePanel("timeline", label="Timeline entry", heading="Timeline"),
        InlinePanel("fun_facts", label="Fun fact", heading="Fun Facts"),
        InlinePanel("words", label="Word", heading="Words to Know"),
        MultiFieldPanel(
            [FieldPanel("think_about_it"), FieldPanel("reflection_question")],
            heading="Think About It and reflection",
        ),
        InlinePanel("quiz_questions", label="Quiz question", heading="Quiz (five questions to publish)"),
        InlinePanel("sources", label="Source", heading="Sources"),
    ]
    promote_panels = Page.promote_panels + [
        MultiFieldPanel(
            [FieldPanel("show_on_homepage"), FieldPanel("featured_sort_order"), FieldPanel("last_source_reviewed_at")],
            heading="Future Saints editorial",
        ),
    ]

    class Meta:
        verbose_name = "Future Saints learning page"

    # --- placement -------------------------------------------------------
    @classmethod
    def can_create_at(cls, parent):
        if not super().can_create_at(parent):
            return False
        kind = getattr(parent.specific, "content_kind", None)
        return kind == cls.content_kind

    def clean(self):
        super().clean()
        if not type(self).content_kind:
            return
        parent = self.get_parent() if self.pk else None
        if parent is not None and getattr(parent.specific, "content_kind", None) != type(self).content_kind:
            raise ValidationError("This learning page type belongs under its own subject index.")

    # --- canonical ---------------------------------------------------------
    @property
    def canonical_page(self):
        page = getattr(self, self.canonical_field, None)
        return page if page is not None and page.live else None

    def quick_fact_sources(self):
        return SITE_SOURCES

    # --- display ------------------------------------------------------------
    @property
    def heading(self):
        return self.student_title or self.title

    @property
    def story_heading(self):
        return "The Story"

    def levels_available(self):
        explorer = _filled(self.explorer_intro) or _filled(self.explorer_story)
        researcher = _filled(self.researcher_intro) or _filled(self.researcher_story)
        return explorer, researcher

    def quick_fact_rows(self):
        canonical = self.canonical_page
        rows = []
        for fact in self.quick_facts.all():
            value = _canonical_value(fact.inherit, canonical) if fact.inherit else _text(fact.value)
            if fact.label and value:
                rows.append({"icon": fact.icon or "star", "label": fact.label, "value": value})
        return rows

    def quiz_data(self):
        data = []
        for question in self.quiz_questions.all():
            choices = [{"text": c.text, "correct": c.is_correct} for c in question.choices.all() if c.text]
            if question.prompt and choices:
                data.append({"prompt": question.prompt, "explanation": question.explanation, "choices": choices})
        return data

    def learning_points(self):
        """Five short points for the research sheet: fun facts first, then timeline text."""
        points = [f.text for f in self.fun_facts.all() if f.text]
        for entry in self.timeline.all():
            text = entry.explorer_text or entry.researcher_text
            if text:
                points.append(text)
        return points[:5]

    def art(self):
        return {
            "hero": _art(self.hero_illustration, self.hero_illustration_alt, self.hero_illustration_credit),
            "context": _art(self.context_illustration, self.context_illustration_alt, self.context_illustration_credit),
            "thumbnail": _art(self.index_thumbnail, self.index_thumbnail_alt, self.index_thumbnail_credit),
        }

    def type_context(self, request):
        """Extra template context for the type-specific blocks."""
        return {}

    def get_template(self, request, *args, **kwargs):
        return "future_saints/learning_page.html"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        explorer, researcher = self.levels_available()
        level = context.get("fs_level") or ""
        if not (explorer and researcher):
            level = "explorer" if explorer else ("researcher" if researcher else "explorer")
        context.update({
            "fs_learning": self,
            "fs_show_level_switch": explorer and researcher,
            "fs_level": level or "explorer",
            "fs_quick_facts": self.quick_fact_rows(),
            "fs_quiz": self.quiz_data(),
            "fs_cards": self.learning_cards,
            "fs_art": self.art(),
            "fs_points": self.learning_points(),
            "fs_type_icon": TYPE_ICONS.get(self.content_kind, "mark"),
        })
        art = context["fs_art"]
        # Credits are listed in this page's own "Sources & Credits" section,
        # so the base template's generic credits line stays empty here.
        context["fs_picture_credits"] = [a["credit"] for a in (art["hero"], art["context"]) if a]
        context["fs_credits"] = []
        context.update(self.type_context(request))
        return context


# --- Repeating items (Orderables with InlinePanels; no StreamField/JSON) ------

class QuickFact(Orderable):
    page = ParentalKey(LearningPage, related_name="quick_facts", on_delete=models.CASCADE)
    icon = models.CharField(max_length=20, blank=True, choices=QUICK_FACT_ICONS)
    label = models.CharField(max_length=40)
    inherit = models.CharField(
        max_length=30, blank=True, choices=INHERIT_CHOICES,
        help_text="Read this value live from the canonical page instead of typing it.",
    )
    value = models.CharField(max_length=120, blank=True, help_text="Leave empty when inheriting.")

    panels = ["icon", "label", "inherit", "value"]


class TimelineEntry(Orderable):
    page = ParentalKey(LearningPage, related_name="timeline", on_delete=models.CASCADE)
    date_display = models.CharField(max_length=60, help_text='As children should read it, e.g. "1991" or "Age 11".')
    explorer_text = models.CharField(max_length=255, blank=True)
    researcher_text = models.CharField(max_length=400, blank=True)

    panels = ["date_display", "explorer_text", "researcher_text"]


class FunFact(Orderable):
    page = ParentalKey(LearningPage, related_name="fun_facts", on_delete=models.CASCADE)
    text = models.CharField(max_length=255)

    panels = ["text"]


class WordToKnow(Orderable):
    page = ParentalKey(LearningPage, related_name="words", on_delete=models.CASCADE)
    word = models.CharField(max_length=60)
    explorer_definition = models.CharField(max_length=255, blank=True)
    researcher_definition = models.CharField(max_length=400, blank=True)

    panels = ["word", "explorer_definition", "researcher_definition"]


class SourceLink(Orderable):
    page = ParentalKey(LearningPage, related_name="sources", on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    url = models.URLField(max_length=500, blank=True)
    publisher = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=255, blank=True, help_text="What this source supports.")

    panels = ["title", "url", "publisher", "note"]


class QuizQuestion(ClusterableModel, Orderable):
    page = ParentalKey(LearningPage, related_name="quiz_questions", on_delete=models.CASCADE)
    prompt = models.CharField(max_length=255)
    explanation = models.CharField(max_length=400, blank=True, help_text="Shown after any answer, kindly.")

    panels = ["prompt", "explanation", InlinePanel("choices", label="Choice", max_num=4)]

    class Meta(Orderable.Meta):
        verbose_name = "quiz question"


class QuizChoice(Orderable):
    question = ParentalKey(QuizQuestion, related_name="choices", on_delete=models.CASCADE)
    text = models.CharField(max_length=160)
    is_correct = models.BooleanField(default=False)

    panels = ["text", "is_correct"]


class BibleReference(Orderable):
    page = ParentalKey("future_saints.HolyLandLearningPage", related_name="bible_references", on_delete=models.CASCADE)
    book = models.CharField(max_length=40)
    chapter = models.PositiveSmallIntegerField()
    verses = models.CharField(max_length=40, blank=True, help_text='e.g. "1-12"')
    url = models.URLField(max_length=500, blank=True, help_text="A reputable Catholic Scripture source.")
    note = models.CharField(max_length=200, blank=True)

    panels = ["book", "chapter", "verses", "url", "note"]

    @property
    def citation(self):
        return f"{self.book} {self.chapter}:{self.verses}" if self.verses else f"{self.book} {self.chapter}"


# --- The five types --------------------------------------------------------------

def _cards(*rows):
    return tuple({"title": t, "line": l, "icon": i, "anchor": a, "wash": w} for t, l, i, a, w in rows)


class SaintLearningPage(LearningPage):
    canonical = models.ForeignKey(
        "catalog.SaintPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        limit_choices_to={"live": True}, help_text="The existing saint page this profile teaches from.",
    )
    saint_name = models.CharField(max_length=80, blank=True, help_text='Builds the title "Meet Saint {name}".')
    story_label = models.CharField(max_length=4, choices=STORY_HEADING_CHOICES, default="the")
    virtues = models.CharField(max_length=200, blank=True, help_text="Key virtues, comma-separated.")
    quote = models.CharField(max_length=300, blank=True, help_text="Only a verifiably sourced quotation.")
    quote_source = models.CharField(max_length=200, blank=True)
    kindness_prompt = models.CharField(max_length=200, blank=True, help_text='"Try a small act of kindness" idea.')

    content_kind = "saint"
    learning_cards = _cards(
        ("The Story", "Read the full story.", "book", "story", "blue"),
        ("Timeline", "See the key events.", "calendar", "timeline", "sage"),
        ("Fun Facts", "Cool things to know!", "lightbulb", "fun-facts", "blue"),
        ("Quiz", "Check what you learned!", "clipboard", "quiz", "lavender"),
    )

    content_panels = Page.content_panels + [
        FieldPanel("canonical"),
        MultiFieldPanel([FieldPanel("saint_name"), FieldPanel("story_label")], heading="Saint"),
    ] + LearningPage.common_panels + [
        MultiFieldPanel(
            [FieldPanel("virtues"), FieldPanel("quote"), FieldPanel("quote_source"), FieldPanel("kindness_prompt")],
            heading="Saintly example",
        ),
    ]

    class Meta:
        verbose_name = "Future Saints saint profile"

    @property
    def heading(self):
        return f"Meet Saint {self.saint_name}" if self.saint_name else super().heading

    @property
    def story_heading(self):
        return dict(STORY_HEADING_CHOICES).get(self.story_label, "The Story")

    def quick_fact_sources(self):
        return SAINT_SOURCES


class MarianLearningPage(LearningPage):
    canonical = models.ForeignKey(
        "catalog.SacredSitePage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        limit_choices_to={"live": True, "category": "Marian Apparition"},
        help_text="The existing apparition page this profile teaches from.",
    )
    witnesses = RichTextField(blank=True, features=SHORT_FEATURES, help_text="Who saw her: the visionaries or witnesses.")
    message = RichTextField(blank=True, features=SHORT_FEATURES, help_text="Mary's message, as the Church presents it.")
    prayer = RichTextField(blank=True, features=SHORT_FEATURES, help_text="A prayer or devotion linked to this apparition.")
    recognition_note = RichTextField(
        blank=True, features=SHORT_FEATURES,
        help_text="Plain words on what the Church's judgment means, and what it does not claim.",
    )

    content_kind = "marian_apparition"
    learning_cards = _cards(
        ("The Story", "Read the full story.", "book", "story", "blue"),
        ("Timeline", "See the key events.", "calendar", "timeline", "sage"),
        ("Mary's Message", "What she asked of us.", "dove", "message", "blue"),
        ("Quiz", "Check what you learned!", "clipboard", "quiz", "lavender"),
    )

    content_panels = Page.content_panels + [FieldPanel("canonical")] + LearningPage.common_panels + [
        MultiFieldPanel(
            [FieldPanel("witnesses"), FieldPanel("message"), FieldPanel("prayer"), FieldPanel("recognition_note")],
            heading="Apparition",
        ),
    ]

    class Meta:
        verbose_name = "Future Saints Marian apparition profile"

    def type_context(self, request):
        canonical = self.canonical_page
        status = _canonical_value("site_status", canonical)
        return {"fs_church_status": status, "fs_recognition_year": _canonical_value("site_recognition_year", canonical)}


class EucharisticLearningPage(LearningPage):
    canonical = models.ForeignKey(
        "catalog.SacredSitePage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        limit_choices_to={"live": True, "category": "Eucharistic Miracle"},
        help_text="The existing Eucharistic miracle page this profile teaches from.",
    )
    belief = RichTextField(blank=True, features=SHORT_FEATURES, help_text="What Catholics believe about the Eucharist, for children.")
    reported = RichTextField(blank=True, features=SHORT_FEATURES, help_text="What was reported, as a historical claim.")
    church_says = RichTextField(blank=True, features=SHORT_FEATURES, help_text="How Church sources understand it.")
    evidence_note = RichTextField(
        blank=True, features=SHORT_FEATURES,
        help_text="What studies or records say, without definitive scientific claims.",
    )

    content_kind = "eucharistic_miracle"
    learning_cards = _cards(
        ("The Story", "Read the full story.", "book", "story", "blue"),
        ("What Happened?", "What people reported.", "scroll", "what-happened", "sage"),
        ("Why It Matters", "What Catholics believe.", "chalice", "why-it-matters", "blue"),
        ("Quiz", "Check what you learned!", "clipboard", "quiz", "lavender"),
    )

    content_panels = Page.content_panels + [FieldPanel("canonical")] + LearningPage.common_panels + [
        MultiFieldPanel(
            [FieldPanel("belief"), FieldPanel("reported"), FieldPanel("church_says"), FieldPanel("evidence_note")],
            heading="Eucharistic miracle",
        ),
    ]

    class Meta:
        verbose_name = "Future Saints Eucharistic miracle profile"


class HolyLandLearningPage(LearningPage):
    canonical = models.ForeignKey(
        "catalog.SacredSitePage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        limit_choices_to={"live": True, "category": "Holy Land"},
        help_text="The existing Holy Land page this profile teaches from.",
    )
    people_places = RichTextField(blank=True, features=SHORT_FEATURES, help_text="The people and places in this story.")
    then_and_now = RichTextField(blank=True, features=SHORT_FEATURES, help_text="History then and the place now. Not travel.")
    what_we_know = RichTextField(blank=True, features=SHORT_FEATURES, help_text="What historians and archaeologists know.")
    tradition = RichTextField(blank=True, features=SHORT_FEATURES, help_text="What tradition says, where it is less certain.")

    content_kind = "holy_land"
    learning_cards = _cards(
        ("Bible Story", "Read what happened here.", "book", "story", "blue"),
        ("Timeline", "See the key events.", "calendar", "timeline", "sage"),
        ("People & Places", "Who was here, and where.", "marker", "people-places", "blue"),
        ("Quiz", "Check what you learned!", "clipboard", "quiz", "lavender"),
    )

    content_panels = Page.content_panels + [FieldPanel("canonical")] + LearningPage.common_panels + [
        InlinePanel("bible_references", label="Bible reference", heading="Find It in the Bible"),
        MultiFieldPanel(
            [FieldPanel("people_places"), FieldPanel("then_and_now"), FieldPanel("what_we_know"), FieldPanel("tradition")],
            heading="Holy Land",
        ),
    ]

    class Meta:
        verbose_name = "Future Saints Holy Land profile"


class MissionLearningPage(LearningPage):
    canonical = models.ForeignKey(
        "catalog.SacredSitePage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        limit_choices_to=Q(live=True) & Q(trail_stops__trail__slug=MISSION_TRAIL_SLUG),
        help_text="The current Mission Trail page (never the older duplicate pages).",
    )
    founding_number = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Founding order 1–21 (not the trail's south-to-north stop order).",
    )
    founding_date = models.DateField(null=True, blank=True)
    founding_date_display = models.CharField(max_length=60, blank=True, help_text='As shown, e.g. "July 16, 1769".')
    founding_source_note = models.CharField(max_length=255, blank=True, help_text="The source for the number and date.")
    native_peoples = RichTextField(blank=True, features=STORY_FEATURES, help_text="Native peoples and mission history, with sources.")
    mission_life = RichTextField(blank=True, features=STORY_FEATURES)
    architecture = RichTextField(blank=True, features=SHORT_FEATURES)

    content_kind = "california_mission"
    learning_cards = _cards(
        ("Mission Story", "Read the full story.", "church", "story", "blue"),
        ("Timeline", "See the key events.", "calendar", "timeline", "sage"),
        ("Native Peoples", "The people who lived here.", "marker", "native-peoples", "blue"),
        ("Build & Quiz", "Build it, then test yourself!", "clipboard", "quiz", "lavender"),
    )

    content_panels = Page.content_panels + [
        FieldPanel("canonical"),
        MultiFieldPanel(
            [FieldPanel("founding_number"), FieldPanel("founding_date"), FieldPanel("founding_date_display"), FieldPanel("founding_source_note")],
            heading="Founding (verified, with a source)",
        ),
    ] + LearningPage.common_panels + [
        MultiFieldPanel([FieldPanel("native_peoples"), FieldPanel("mission_life"), FieldPanel("architecture")], heading="Mission"),
    ]

    class Meta:
        verbose_name = "Future Saints California mission profile"

    def clean(self):
        super().clean()
        if self.founding_number is not None and not 1 <= self.founding_number <= 21:
            raise ValidationError({"founding_number": "Founding numbers run from 1 to 21."})

    def type_context(self, request):
        siblings = (
            MissionLearningPage.objects.sibling_of(self, inclusive=True).live()
            .exclude(founding_number=None).order_by("founding_number")
        )
        chain = [{"number": p.founding_number, "title": p.heading, "date": p.founding_date_display,
                  "url": p.get_url(request), "current": p.pk == self.pk} for p in siblings]
        return {"fs_founding_chain": chain}
