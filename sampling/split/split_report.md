# Dev/test split

Written for: the team. Made by `sampling/make_dev_test_split.py` with seed 42. Do not redraw it once prompt tuning has started.

Dev and test keep the natural share of useful articles. Few-shot examples come from dev only.

| set | dev useful | dev total | test useful | test total |
|---|---|---|---|---|
| all | 106 | 397 | 209 | 803 |

| labeler | dev useful | dev total | test useful | test total |
|---|---|---|---|---|
| Aditya | 24 | 104 | 48 | 196 |
| Jahnavi | 27 | 99 | 50 | 201 |
| Manoj | 29 | 100 | 57 | 200 |
| Thanya | 26 | 94 | 54 | 206 |

| country | dev useful | dev total | test useful | test total |
|---|---|---|---|---|
| AUS | 27 | 91 | 42 | 150 |
| BRA | 3 | 44 | 6 | 89 |
| IDN | 2 | 27 | 9 | 67 |
| IND | 31 | 107 | 69 | 212 |
| KEN | 1 | 18 | 8 | 58 |
| USA | 42 | 110 | 75 | 227 |

| year | dev useful | dev total | test useful | test total |
|---|---|---|---|---|
| 2015 | 6 | 25 | 18 | 44 |
| 2016 | 18 | 49 | 38 | 100 |
| 2017 | 16 | 35 | 21 | 68 |
| 2018 | 10 | 45 | 23 | 89 |
| 2019 | 3 | 17 | 10 | 48 |
| 2021 | 3 | 35 | 11 | 80 |
| 2022 | 17 | 79 | 25 | 141 |
| 2023 | 17 | 59 | 17 | 100 |
| 2024 | 16 | 53 | 46 | 133 |

| bucket | dev useful | dev total | test useful | test total |
|---|---|---|---|---|
| N_animal_flu | 1 | 24 | 2 | 51 |
| N_awareness | 1 | 37 | 3 | 73 |
| N_business_policy | 1 | 7 | 0 | 13 |
| N_flu_idiom | 0 | 10 | 1 | 20 |
| N_history_only | 1 | 14 | 1 | 26 |
| N_no_flu_text | 0 | 14 | 0 | 36 |
| N_other_disease | 0 | 20 | 0 | 40 |
| N_other_flu_mention | 6 | 49 | 10 | 101 |
| N_research | 0 | 13 | 0 | 27 |
| P_A1_counts | 46 | 80 | 92 | 160 |
| P_A2_case_event | 19 | 44 | 36 | 86 |
| P_B_trend_response | 26 | 66 | 54 | 134 |
| X_listing_garbled | 0 | 2 | 0 | 2 |
| X_spam_stub | 0 | 2 | 0 | 2 |
| X_too_short | 0 | 5 | 1 | 12 |
| Z_zoonotic_human | 5 | 10 | 9 | 20 |

## Same-story groups

21 groups hold 49 articles that tell the same story; each group sits in one set.

| group | articles | set |
|---|---|---|
| 20150717011500-230 | 2 | dev |
| 20151126031500-1370 | 2 | dev |
| 20160114154500-826 | 2 | dev |
| 20160130104500-564 | 2 | dev |
| 20170119031500-764 | 2 | dev |
| 20171218211500-883 | 2 | test |
| 20180106084500-1487 | 6 | test |
| 20180622131500-1587 | 2 | dev |
| 20180803133000-889 | 2 | dev |
| 20181025180000-1632 | 2 | dev |
| 20191202214500-1023 | 2 | dev |
| 20210812141500-261 | 2 | dev |
| 20211020113000-649 | 2 | dev |
| 20211207163000-398 | 2 | test |
| 20220723003000-988 | 3 | dev |
| 20220724204500-399 | 2 | dev |
| 20220930024500-847 | 4 | dev |
| 20230112123000-52 | 2 | dev |
| 20230526201500-617 | 2 | dev |
| 20240104000000-183 | 2 | test |
| 20240118030000-940 | 2 | dev |

## Rule tags

Each tag needs min(3, half its total) dev articles. 6 swaps between matched groups were made to get there.

| tag | dev | test | dev minimum |
|---|---|---|---|
| count:comparison_nearby | 10 | 8 | 3 |
| count:new_and_total | 17 | 23 | 3 |
| count:open_total | 20 | 32 | 3 |
| count:period_total | 34 | 52 | 3 |
| date:last_month | 1 | 2 | 2 |
| date:last_week | 7 | 11 | 3 |
| date:none_stated | 2 | 1 | 2 |
| date:past_week | 3 | 4 | 3 |
| date:since | 11 | 26 | 3 |
| date:so_far_this_year | 5 | 8 | 3 |
| date:this_season | 5 | 13 | 3 |
| date:week_ending | 3 | 8 | 3 |
| date:week_number | 2 | 1 | 2 |
| date:weekday | 16 | 35 | 3 |
| date:yesterday | 4 | 3 | 3 |
| kind:cases | 53 | 91 | 3 |
| kind:deaths | 30 | 63 | 3 |
| kind:hospitalized | 19 | 29 | 3 |
| kind:trend | 71 | 125 | 3 |
| no:N_animal_flu | 23 | 49 | 3 |
| no:N_awareness | 36 | 70 | 3 |
| no:N_business_policy | 6 | 13 | 3 |
| no:N_flu_idiom | 10 | 19 | 3 |
| no:N_history_only | 13 | 25 | 3 |
| no:N_no_flu_text | 14 | 36 | 3 |
| no:N_other_disease | 20 | 40 | 3 |
| no:N_other_flu_mention | 43 | 91 | 3 |
| no:N_research | 13 | 27 | 3 |
| no:P_A1_counts | 34 | 68 | 3 |
| no:P_A2_case_event | 25 | 50 | 3 |
| no:P_B_trend_response | 40 | 80 | 3 |
| no:X_listing_garbled | 2 | 2 | 2 |
| no:X_spam_stub | 2 | 2 | 2 |
| no:X_too_short | 5 | 11 | 3 |
| no:Z_zoonotic_human | 5 | 11 | 3 |
| no:word_rules_said_useful | 104 | 209 | 3 |
| note:animal | 15 | 37 | 3 |
| note:forecast | 5 | 16 | 3 |
| note:in_passing | 15 | 35 | 3 |
| note:no_country | 4 | 4 | 3 |
| note:past | 4 | 16 | 3 |
| place:several_countries | 8 | 14 | 3 |
| place:territory | 3 | 5 | 3 |
| status:suspected | 6 | 11 | 3 |
| strain:animal_flu_in_people | 9 | 23 | 3 |
| trend:percentage | 6 | 16 | 3 |
| trend:strain_share | 6 | 6 | 3 |
| trend:zero_or_low | 6 | 8 | 3 |
| yes:word_rules_said_not_useful | 10 | 18 | 3 |

Tags that could not reach their minimum: date:last_month.

## Check rows that still disagree with the owner

None.

## Label corrections after the split (2026-10-19)

The 3 round-1 check rows that disagreed were settled by the rulebook. The split itself did not change.

| article | set | decision |
|---|---|---|
| 20221106180000-54 | test | `no`: flu is only named in a list in an RSV vaccine article (Thanya's label changed; Jahnavi's check was right) |
| 20240212170000-2059 | test | `yes`: a named rider was suffering from flu at this week's event (Aditya's label stands) |
| 20181030023000-1998 | test | `yes`: "There has already been a flu-related death in Florida this year." (Aditya's label stands; changed to `no` in review round 3, see below) |
| 20160620113000-1875 | dev | `yes`: the Prime Minister has the flu, from Saturday; one named person is enough (Thanya's label changed) |
| 20161106151500-1403 | dev | `yes`: "in the year 2016, only one case has been reported so far" is a current running total (Jahnavi's label changed) |
| 20171201021500-1341 | dev | `yes`: Dame Joan Collins was "ill with the flu" for Wednesday's launch; one named person (Manoj's label changed) |
| 20150605213000-2429 | test | `yes`: the state's swine flu toll "now stands at 535" since January, with two new deaths (Jahnavi's label changed) |
| 20191120054500-149 | test | `yes`: Sheriff Chuck Wright "who is battling the flu"; one named person (Manoj's label changed) |
| 20150603061500-239 | test | `yes`: Priyanka Chopra's doctor said it was influenza, on Tuesday; one named person (Manoj's label changed) |
| 20240623111500-759 | test | `yes`: "three humans in the U.S. have been diagnosed" with H5N1 during the dairy outbreak, the latest within 30 days (Manoj's label changed) |

Rows 4 and 5 were found on 2026-10-19 while choosing the prompt v2.1 examples. The last five were found the same day by the second rulebook audit of all four sheets (`labeling_harmonisation/audit_round2/`), which also fixed items in 49 articles (22 dev, 27 test). The counts and tags above include all ten corrections and those item fixes.

## Review round 3 (2026-10-19)

Jahnavi reviewed all four sheets (on copies from before round 2). The team settled her changes against the
rulebook, with no model output. The 13 label changes below, plus item fixes in 31 more articles (7 dev, 24 test), are in
`labeling_harmonisation/change_logs/review_round3_changes.txt`. The split itself did not change.

| article | set | decision |
|---|---|---|
| 20181030023000-1998 | test | `no`: team decision: one undated line in a flu-drug story; the period since January is too long to place the event (Aditya's label and Manoj's check row changed) |
| 20160423230000-1664 | dev | `no`: team decision: a salt-cave promotion story; flu is only the opening phrase "As flu season begins" (Aditya's label changed) |
| 20181025180000-1632 | dev | `no`: the only flu line is a bracketed link to another story, with no place or date (Aditya's label changed) |
| 20231218161500-1115 | test | `no`: the only human figure is a lifetime US H5N1 total, the latest case in April 2022; background (Aditya's label changed) |
| 20241219053000-302 | test | `no`: the only flu words are a "Read more" link to another article (Manoj's label changed) |
| 20220426101500-125 | test | `no`: team decision: "Quebec experienced a late flu season" is background in a COVID staffing story (Manoj's label changed) |
| 20161227231500-2770 | test | `no`: the strain sentences describe last year's season; "gears up for flu season" is preparation (Thanya's label changed) |
| 20160707183000-1141 | dev | `no`: team decision: the page is a February 2015 news roundup collected in July 2016 ("Obama paid a formal visit to India three weeks ago"), so its swine flu counts are not current (Thanya's label changed) |
| 20181218064500-764 | test | `yes`: former president Moi was admitted to Nairobi Hospital last Thursday and treated for flu; one named person (Manoj's label changed) |
| 20230329193000-2321 | dev | `yes`: President Lula was diagnosed with bronchopneumonia caused by influenza A; one named person (Manoj's label changed) |
| 20240405130000-123 | test | `yes`: the first human H5N1 case in Texas "this week", a dairy farm worker (Manoj's label changed) |
| 20181205114500-124 | test | `yes`: Kansas flu activity is still listed as "sporadic", a current low level (Thanya's label changed) |
| 20221025141500-417 | dev | `yes`: a Tennessee specialist: "As of today, we are seeing equal numbers of Covid, flu and RSV", "very early for flu" (Thanya's label changed) |

Dev goes from 107 to 106 useful articles; test goes from 211 to 209. The tag `date:last_month` is now one
dev article short of its minimum: article 20150605213000-2429 (test) correctly got "last month" dates, which
raised the minimum from 1 to 2. The frozen split is not redrawn for this.
