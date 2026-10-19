# Dev/test split

Written for: the team. Made by `sampling/make_dev_test_split.py` with seed 42. Do not redraw it once prompt tuning has started.

Dev and test keep the natural share of useful articles. Few-shot examples come from dev only.

| set | dev useful | dev total | test useful | test total |
|---|---|---|---|---|
| all | 104 | 397 | 208 | 803 |

| labeler | dev useful | dev total | test useful | test total |
|---|---|---|---|---|
| Aditya | 26 | 104 | 50 | 196 |
| Jahnavi | 26 | 99 | 49 | 201 |
| Manoj | 27 | 100 | 54 | 200 |
| Thanya | 25 | 94 | 55 | 206 |

| country | dev useful | dev total | test useful | test total |
|---|---|---|---|---|
| AUS | 28 | 91 | 41 | 150 |
| BRA | 2 | 44 | 6 | 89 |
| IDN | 2 | 27 | 8 | 67 |
| IND | 30 | 107 | 67 | 212 |
| KEN | 1 | 18 | 8 | 58 |
| USA | 41 | 110 | 78 | 227 |

| year | dev useful | dev total | test useful | test total |
|---|---|---|---|---|
| 2015 | 6 | 25 | 16 | 44 |
| 2016 | 18 | 49 | 39 | 100 |
| 2017 | 15 | 35 | 21 | 68 |
| 2018 | 11 | 45 | 22 | 89 |
| 2019 | 3 | 17 | 9 | 48 |
| 2021 | 3 | 35 | 11 | 80 |
| 2022 | 16 | 79 | 27 | 141 |
| 2023 | 16 | 59 | 18 | 100 |
| 2024 | 16 | 53 | 45 | 133 |

| bucket | dev useful | dev total | test useful | test total |
|---|---|---|---|---|
| N_animal_flu | 1 | 24 | 2 | 51 |
| N_awareness | 1 | 37 | 3 | 73 |
| N_business_policy | 1 | 7 | 0 | 13 |
| N_flu_idiom | 0 | 10 | 1 | 20 |
| N_history_only | 1 | 14 | 1 | 26 |
| N_no_flu_text | 0 | 14 | 0 | 36 |
| N_other_disease | 0 | 20 | 1 | 40 |
| N_other_flu_mention | 5 | 49 | 9 | 101 |
| N_research | 0 | 13 | 0 | 27 |
| P_A1_counts | 45 | 80 | 91 | 160 |
| P_A2_case_event | 18 | 44 | 34 | 86 |
| P_B_trend_response | 27 | 66 | 55 | 134 |
| X_listing_garbled | 0 | 2 | 0 | 2 |
| X_spam_stub | 0 | 2 | 0 | 2 |
| X_too_short | 0 | 5 | 1 | 12 |
| Z_zoonotic_human | 5 | 10 | 10 | 20 |

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
| count:comparison_nearby | 9 | 7 | 3 |
| count:new_and_total | 14 | 17 | 3 |
| count:open_total | 17 | 30 | 3 |
| count:period_total | 33 | 48 | 3 |
| date:last_month | 1 | 0 | 1 |
| date:last_week | 7 | 11 | 3 |
| date:none_stated | 3 | 3 | 3 |
| date:past_week | 3 | 4 | 3 |
| date:since | 10 | 22 | 3 |
| date:so_far_this_year | 5 | 7 | 3 |
| date:this_season | 5 | 13 | 3 |
| date:week_ending | 3 | 7 | 3 |
| date:week_number | 2 | 1 | 2 |
| date:weekday | 14 | 30 | 3 |
| date:yesterday | 3 | 2 | 3 |
| kind:cases | 50 | 83 | 3 |
| kind:deaths | 31 | 62 | 3 |
| kind:hospitalized | 16 | 22 | 3 |
| kind:trend | 67 | 124 | 3 |
| no:N_animal_flu | 23 | 49 | 3 |
| no:N_awareness | 36 | 70 | 3 |
| no:N_business_policy | 6 | 13 | 3 |
| no:N_flu_idiom | 10 | 19 | 3 |
| no:N_history_only | 13 | 25 | 3 |
| no:N_no_flu_text | 14 | 36 | 3 |
| no:N_other_disease | 20 | 39 | 3 |
| no:N_other_flu_mention | 44 | 92 | 3 |
| no:N_research | 13 | 27 | 3 |
| no:P_A1_counts | 35 | 69 | 3 |
| no:P_A2_case_event | 26 | 52 | 3 |
| no:P_B_trend_response | 39 | 79 | 3 |
| no:X_listing_garbled | 2 | 2 | 2 |
| no:X_spam_stub | 2 | 2 | 2 |
| no:X_too_short | 5 | 11 | 3 |
| no:Z_zoonotic_human | 5 | 10 | 3 |
| no:word_rules_said_useful | 105 | 210 | 3 |
| note:animal | 15 | 35 | 3 |
| note:forecast | 5 | 16 | 3 |
| note:in_passing | 14 | 35 | 3 |
| note:no_country | 4 | 4 | 3 |
| note:past | 3 | 13 | 3 |
| place:several_countries | 7 | 11 | 3 |
| place:territory | 3 | 4 | 3 |
| status:suspected | 6 | 11 | 3 |
| strain:animal_flu_in_people | 9 | 22 | 3 |
| trend:percentage | 6 | 15 | 3 |
| trend:strain_share | 5 | 6 | 3 |
| trend:zero_or_low | 5 | 8 | 3 |
| yes:word_rules_said_not_useful | 9 | 18 | 3 |

Tags that could not reach their minimum: none.

## Check rows that still disagree with the owner

| article | owner | owner says | checker | checker says |
|---|---|---|---|---|
| 20221106180000-54 | Thanya | yes | Jahnavi | no |
| 20240212170000-2059 | Aditya | yes | Manoj | no |
| 20181030023000-1998 | Aditya | yes | Manoj | no |

The owner's label is used. Settle these with the team.
