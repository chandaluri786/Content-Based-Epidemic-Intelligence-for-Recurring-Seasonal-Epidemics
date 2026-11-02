# Few-shot example candidates (prompt v5.1)

Written by `scripts/select_examples.py`. The k = 8 set is the active `prompts/examples_v5.1.json`. Picks favour hard cases: a `hard_case` note and articles the model got wrong in earlier runs.

Pool: 573 labelled records after exclusions (article over 6000 characters (10000 for hard_case): 197, in more than one labeling set: 80, fails the keyword gate: 44, reply over 5000 characters: 25, garbled text: 1).

## Coverage by size

| k | Slots covered | Rules covered | Not useful | Labelers | Approx. extra tokens per call |
|---|---|---|---|---|---|
| 4 | 10 of 12 | 36 of 68 | 1 | Jahnavi 2, Aditya 1, Manoj 1 | ~7,370 |
| 8 | 12 of 12 | 40 of 68 | 3 | Jahnavi 3, Aditya 2, Manoj 3 | ~12,649 |
| 12 | 12 of 12 | 46 of 68 | 4 | Jahnavi 4, Aditya 4, Manoj 4 | ~17,294 |

## The 12 candidates, in selection order (the first 4 are k=4, the first 8 are k=8)

| # | Source | Article id | Useful | Slots | Kinds | Countries | Characters | Hardness | Why hard |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Jahnavi:83 | 20160129010000-168 | yes | 6, 7, 9, 10, 11, 12 | cases, deaths, trend | Turkey | 6,531 | 1.0 | run_k0_D: items under 50%; run_k8_D: items under 50% |
| 2 | Jahnavi:311 | 20240429194500-29 | no | 2, 3 | - | - | 6,684 | 1.0 | run_k0_D: useful wrong; run_k8_D: useful wrong |
| 3 | Aditya:307 | 20220829023000-469 | yes | 4, 10 | trend | USA | 11,698 | 2.0 | hard_case: 1.3 monitoring statement comes from a general CDC update, with no group or numbe |
| 4 | Manoj:79 | 20240509071500-893 | yes | 5, 10, 11, 12 | deaths, hospitalized | India | 4,567 | 1.0 | run_k0_D: items under 50%; run_k8_D: items under 50% |
| 5 | Jahnavi:320 | 20231212123000-536 | no | 1 | - | - | 2,884 | 2.0 | hard_case: S1 is China's own statement of 'normal flu', which the letter rejects. 1.2 decid |
| 6 | Manoj:162 | 20171213001500-2183 | yes | 8, 9 | trend | Canada, Central African Republic, Cote d'Ivoire, Ghana, Mexico, Mozambique, USA | 7,848 | 0.5 | run_k8_D: items under 50% |
| 7 | Aditya:142 | 20160630003000-1352 | yes | - | trend | Australia, Bolivia, Brazil, Colombia, New Zealand, Panama | 7,106 | 1.0 | run_k0_D: items under 50%; run_k8_D: items under 50% |
| 8 | Manoj:60 | 20240119024500-96 | no | 3 | - | - | 3,281 | 1.0 | run_k0_D: useful wrong; run_k8_D: useful wrong |
| 9 | Jahnavi:308 | 20241107220000-969 | yes | 6, 10, 11 | cases | USA | 7,924 | 2.0 | hard_case: S4: eight workers with antibodies, dated to the summer by 4.3.3, so no item; a r |
| 10 | Manoj:213 | 20160113143000-549 | no | 1 | - | - | 2,522 | 1.0 | run_k0_D: useful wrong; run_k8_D: useful wrong |
| 11 | Aditya:211 | 20240606170000-637 | yes | - | cases | Mexico | 3,735 | 1.0 | run_k0_D: items under 50%; run_k8_D: items under 50% |
| 12 | Aditya:320 | 20240610041500-300 | yes | 4, 9 | trend | Australia | 4,396 | 1.0 | run_k0_D: useful wrong; run_k8_D: useful wrong |

Rules used in the pool but in none of the 12: 5.3.6, 5.3.3, 4.3.4, 9.3.1, 9.3.7, 9.4, 9.3.6, 9.5.3, 9.3.4, 5.3.7, 9.5.2, 6.3.1, 9.3.3, 5.1, 3.1, 4.3.2, 5.3, 8.3, 6.3.4, 9.5.4, 4.3, 6.3.3.

## Alternates per slot (up to 3, shortest first)

| Slot | Rules | Chosen | Alternates |
|---|---|---|---|
| 1. Flu named, but no current activity | 1.2, 9.5 | Jahnavi:320, Manoj:213 | Jahnavi:214, Jahnavi:282, Aditya:47 |
| 2. Flu in animals only | 1.3 | Jahnavi:311 | Jahnavi:187, Aditya:244, Jahnavi:243 |
| 3. Past or forecast | 4.1, 4.7, 9.3.8 | Jahnavi:311, Manoj:60 | Aditya:77, Aditya:113, Aditya:121 |
| 4. Food link fallback | 1.3, 9.7 | Aditya:307, Aditya:320 | Aditya:239, Aditya:241, Jahnavi:248 |
| 5. Stages for one person | 2.4, 4.3 | Manoj:79 | Manoj:181, Manoj:185, Aditya:54 |
| 6. Overlapping counts | G4, G5 | Jahnavi:83, Jahnavi:308 | Jahnavi:85, Manoj:289, Manoj:185 |
| 7. Count and trend together | 2.3, 9.3 | Jahnavi:83 | Aditya:183, Jahnavi:58, Manoj:86 |
| 8. Fallback present, per place | 9.3.5, 9.7 | Manoj:162 | Manoj:115, Jahnavi:171, Manoj:47 |
| 9. Trend with a strain | 9.6 | Jahnavi:83, Manoj:162, Aditya:320 | Manoj:66, Manoj:131, Aditya:241 |
| 10. Place from context | 5.3.6, 5.4, 5.5 | Jahnavi:83, Aditya:307, Manoj:79, Jahnavi:308 | Manoj:74, Manoj:202, Aditya:318 |
| 11. Relative dates | 4.3-4.6 | Jahnavi:83, Manoj:79, Jahnavi:308 | Manoj:96, Aditya:318, Aditya:208 |
| 12. Subset vs region, suspected | 6.3, 7.2 | Jahnavi:83, Manoj:79 | Manoj:96, Aditya:318, Manoj:86 |
