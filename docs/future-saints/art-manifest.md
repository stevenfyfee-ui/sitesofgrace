# Future Saints: art manifest (Phase 1 slots)

No art was generated or downloaded for Phase 1. Every slot currently shows the placeholder art frame
(staff also see the slot name on it).

**Rule enforced in code:** an illustration appears only when its image AND its credit field are filled
in the admin. A saint portrait (Saint of the Week) appears only when the SaintPage's `portrait_credit`
is filled. There is no fallback to an uncredited canonical image. Credits are listed under "Pictures:"
at the foot of the page.

Style for every slot (brief §2): the approved watercolor look of the three comps; warm ivory and
parchment grounds; gold and powder-blue accents; no bright preschool palette; no cartoon mascots;
nothing infantilizing Mary or the saints. Comps are layout and mood references only: never slice,
trace, stretch or embed them.

| # | slot (admin field) | aspect (crop) | min source px | rendered as | subject notes (from the comps / brief) | licence / credit |
|---|---|---|---|---|---|---|
| 1 | Homepage hero (`hero_illustration`) | 16:10 | 3200 × 2000 | fill-1600x1000 | Comp 01: an unrolled parchment world map with a dotted pilgrimage route; compass; small globe; stacked books; small vignettes on the map: a Franciscan saint with a bird, Mary in clouds with a ring of stars, a chalice and host in soft rays, a white mission church with a bell. Left edge stays calm (the headline sits beside it, not on it). | |
| 2 | Card 1, Meet the Saints (`card_1_illustration`) | 4:3 (16:9 crop on phones, keep subject centered) | 1600 × 1200 | fill-800x600 | Comp 01 card 1: a friar saint in a brown habit with halo, a small bird on his hand, leafy trees. Sage band below. | |
| 3 | Card 2, Mary & Apparitions (`card_2_illustration`) | 4:3 (16:9 on phones) | 1600 × 1200 | fill-800x600 | Comp 01 card 2: Mary praying in white and blue, a ring of stars, roses, a rocky grotto with candles. Dignified, not doll-like. Blue band. | |
| 4 | Card 3, Eucharistic Miracles (`card_3_illustration`) | 4:3 (16:9 on phones) | 1600 × 1200 | fill-800x600 | Comp 01 card 3: a golden chalice with the host, subdued radiating rays, warm gold-to-rose ground. No claim-like imagery (no blood, no lab). Gold band. | |
| 5 | Card 4, California Missions (`card_4_illustration`) | 4:3 (16:9 on phones) | 1600 × 1200 | fill-800x600 | Comp 01 card 4: a white stucco mission facade with a bell tower, red tile roof, palms, bougainvillea. Generic: must not imply one specific mission unless it is accurate to that mission. Terracotta band (the comp's lavender is reserved for Quiz cards). | |
| 6 | Holy Land feature (`holy_land_illustration`) | 16:9; on ≥768 px it fills a panel about 3:2 (center the subject) | 1920 × 1080 | fill-1600x900 | Not in the comps (new requirement). Brief §2: sandstone, olive and sage tones, Biblical-era geography, e.g. Judean hills, olive trees, a historically appropriate stone town or church silhouette. No modern travel cues (no buses, hotels, crowds, signage). | |
| 7 | Saints index banner (`banner_illustration`) | 16:9 | 1600 × 900 | fill-1600x900 | Saints, gold/blue (brief table). A group of saints or a saintly scene, consistent with card 2's family of art. | |
| 8 | Mary & Apparitions index banner | 16:9 | 1600 × 900 | fill-1600x900 | Marian blue, roses, stars; a recognizable but non-specific apparition setting. | |
| 9 | Eucharistic Miracles index banner | 16:9 | 1600 × 900 | fill-1600x900 | Gold/ivory; monstrance or chalice and host; subdued rays. | |
| 10 | Holy Land index banner | 16:9 | 1600 × 900 | fill-1600x900 | Sandstone/olive/sage landscape; may share a palette with slot 6 but should not be the same picture. | |
| 11 | California Missions index banner | 16:9 | 1600 × 900 | fill-1600x900 | Parchment/copper/sage; mission silhouette, poppies. Phase 3 replaces this index with the illustrated 21-mission map hub (comp 02); that map is separate art and not part of this manifest. | |
| 12 | Saint portrait frame (Saint of the Week; SaintPage `portrait` + `portrait_credit`) | 1:1, shown in a circle with a gold ring | 800 × 800 | fill-400x400 | Uses the canonical saint's portrait only when `portrait_credit` is filled. Keep the face in the middle 60% (the circle crops the corners). Comp 01 shows St. Francis of Assisi; locally and in production his page has no portrait. | |

Credits to record per image (in the slot's credit field): artist or source, licence (e.g. "Commissioned
for Sites of Grace, all rights assigned", "CC BY 4.0, <author>", "Public domain"), and for photos the
correct modern vs. historic identification. The credit text is shown to readers.

Production records relevant to slot 12 (content audit): St. Carlo Acutis has a portrait (img#43) with
**no credit**; St. Francis of Assisi has **no portrait**.
