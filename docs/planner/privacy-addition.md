# Privacy Policy addition: saved trips (draft for review)

**Status:** approved and in `legal/content/privacy-policy.md` (November 2026). The production Privacy Policy
draft (LegalPage 2502) was rebuilt from that file by `tools/rebuild_privacy_draft.py` as draft revision 1395,
not published. It goes live with the other legal pages through `publish_legal_pages`, with the effective date
set to the publish day, no later than the day `SOG_PLANNER_V2` goes to "on".

The policy's existing numbered sections stay as they are. These are three short additions, worded to match the
rest of the policy.

---

## 1. Add to "2. Information we collect" (new bullet, after "Pilgrimage and community information")

- **Saved trips:** if you save a plan from the trip planner, we store the trip's name, its destinations and
  the number of nights in each, your start date if you gave one, the number of travelers, and the lodging and
  pace you chose. We never store prices. The estimated budget is worked out again from our current figures
  each time you open the trip. If you use the planner without saving, your plan lives only in the page's web
  address, and we do not keep it.

## 2. Add to "4. When information is public" (new paragraph, at the end of the section)

Your saved trips are private. Only you can see them, unless you turn on a share link for a trip. Anyone who
has a trip's share link can view that trip's name and plan, even without an account. They cannot see your
name, username, email address, or anything else about your account, and they cannot change your trip. The
link is long and hard to guess, but anyone you send it to can pass it on. If you turn the link off, it stops
working right away. If you turn sharing on again later, you get a new link, and the old one still won't work.
Shared trip pages ask search engines not to list them.

## 3. Add to "8. How long we keep information" (new bullet, after "Account information, saved places, and your photo library")

- **Saved trips and their share links:** while your account is open, or until you delete the trip. When you
  delete a trip, or when your account is deleted, the trip and any share link are deleted with it.

---

## Notes for review (not for publication)

- **Accuracy check against the code:**
  - The fields listed are exactly the `Trip` and `TripStop` fields: title, start date, party, tier and pace,
    plus each stop's destination and nights.
  - Prices are never stored; the budget is rebuilt on every view.
  - Share tokens come from `secrets.token_urlsafe(16)`. Turning sharing off clears the token, and turning it
    on again makes a new one.
  - The shared view sends `noindex`, both as a meta tag and as an `X-Robots-Tag` header, and shows no
    account details.
  - `owner` uses `on_delete=CASCADE`, so deleting the account deletes its trips.
- **"While your account is open":** matches section 8 as written. Self-serve account deletion arrives in pilgrim
  portal Phase 5. Until then, deletion is by email request, as section 9 already says, and trips go with the
  account through the same cascade.
- **No new IP use:** the planner's search and plan endpoints rate-limit with the same hashed-IP cache counter
  section 2 already describes ("We also use IP addresses briefly to limit abuse"). Saving trips counts the
  account's own recent saves, not IPs. So section 2's "Technical information" bullet needs no change.
- **Booking links (Phase 5):** when they are switched on, the outbound click count stores no IP, user or
  cookie, only the link, the first stop's destination, the date and a count. The Affiliate Disclosure,
  not this policy, covers the commission. If the travel providers' own privacy practices need a sentence here,
  add it under "5. Who we share information with" when the links go live.
- **Reading level:** about 7th to 8th grade, with short sentences and no legal terms.
