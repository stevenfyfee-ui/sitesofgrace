# Standing rules for every v2 phase
1. Branch. Work only on `pilgrimage-v2`, created from an up-to-date main. Never commit to main, never
   push main, never merge into main, never force-push. Push the branch only when I say "push".
2. Autopush. If AUTOPUSH-BLOCKED.txt exists, read it to me first. Make sure .autopush-pause exists
   (create it if not, and say whether it was already there). Leave it in place.
3. Feature switch. All new public-facing UI renders only when the switch allows it. settings.SOG_V2_ENABLED
   reads env var SOG_V2_ENABLED: "off" (default), "staff" (request.user.is_staff only), "on". Use one
   helper everywhere (a Python function v2_enabled(request) and a matching template tag). With "off",
   every existing page renders as it does today, apart from fixes marked ALWAYS ON.
4. Data model. Additive migrations only. Nullable fields; choice fields with a blank option. Discrete
   fields, not StreamField. Never delete or rewrite existing content or fields. Never overwrite a filled
   field from code.
5. No invented facts. Sample data lives only in `manage.py v2_dev_sample`, which refuses to run unless
   settings.DEBUG is True and the database is not production. Every sample row's name contains
   "(sample)". Real content comes through the admin or a JSON import that follows
   docs/v2/IMPORT-RULES.md.
6. Style. Existing palette tokens and classes (Marian Navy, Sky Blue, Sacred Gold, Parchment, Ivory;
   Cinzel, Cormorant Garamond, Lora). No new colors beyond the mockup's.
7. Maps. Every new map uses Leaflet exactly like the Interactive Map: the shared basemap via
   SoGBasemap.add(map) from static/js/basemap.js (never a new L.tileLayer), maxZoom 16, sites drawn as
   L.circleMarker dots colored from CATEGORY_STYLES in their own pane above lines, radius from the same
   radiusFor(zoom) curve, no clustering, and no permanent name labels (tooltips on hover/focus and
   popups are fine). Put shared map code in one new file, static/js/sog-maps.js, rather than copying it.
8. Code hygiene. ast.parse every Python file before saving and read each file back after writing.
   {% comment %}…{% endcomment %} for multi-line template comments. Preserve each file's existing line
   endings. Keyboard access and visible focus for every new control. Pages work without JavaScript.
9. Commercial links. Any affiliate or partner link gets rel="sponsored nofollow noopener" and a
   disclosure sentence right next to it, linking to an Affiliate Disclosure page if one is live.
10. Privacy. No third-party analytics, geocoders or Google Places. No visitor IPs stored. No production
    data copied to the laptop.
11. Tests. Each phase adds tests. Before every STOP run: manage.py check, makemigrations --check, the
    phase's app tests, then the full suite. Report counts.
12. Every phase ends with a STOP: collectstatic, runserver, `v2_dev_sample`, SOG_V2_ENABLED=on locally,
    then screenshot the affected pages at 1440 and 390 into
    C:\Users\steve\Downloads\sog-v2-shots\phase-<n>\ . Also screenshot the same page with
    SOG_V2_ENABLED=off to prove nothing changed. List every place you differ from the mockup and why.
    Wait. When I say "go", stage only this phase's files by explicit path and make one scoped commit on
    pilgrimage-v2.
