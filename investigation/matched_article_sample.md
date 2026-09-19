# Random Sample of Matched Articles, Per Country

Raw, unfiltered, unanalyzed sample for manual inspection. Each row is one line from data/gdelt_matched/{COUNTRY}.jsonl as ingested by Step 2 -- no article text was fetched or read to produce this list.

**On "article title": not available.** The matched-article files only ever store {stamp, url} per line (see pipeline/cli/run_step2_ingest.py's ThreadSafeMatchWriter) -- no title, headline, or any other metadata is captured at match time. Getting a title would require fetching the live article, which was explicitly out of scope here. The "GDELT-tagged country" for every row in a section is the country name of that section (i.e. which {COUNTRY}.jsonl file the row came from) -- GDELT can tag the same URL to more than one country if the article mentions multiple countries' locations (see pipeline/gdelt/flu_filter.py -- one match is written per matching target country).

**Matched date**: the stamp column is the GDELT 15-minute snapshot timestamp (YYYYMMDDHHMMSS) at which this URL was seen in that day's GKG feed -- this is when GDELT indexed the article, not necessarily its publish date.

## USA (58458 total matched articles; 20 sampled)

| Stamp (GDELT snapshot, UTC) | URL |
|---|---|
| 2015-12-29 13:30 | http://www.jamestownsun.com/news/state/3913070-flu-cases-may-peak-late-season |
| 2016-01-13 17:15 | http://www.fox30jax.com/news/news/health-med-fit-science/new-strain-highly-contagious-dog-flu-appears-king-/np4L7/ |
| 2016-02-13 10:15 | http://www.grandforksherald.com/news/region/3946919-flu-numbers-pick-mild-season-still-possible |
| 2016-12-19 21:45 | http://wspa.com/2016/12/19/hendersonville-hospital-limiting-visitors-due-to-flu-like-symptoms/ |
| 2017-01-14 00:15 | http://www.tribstar.com/cnhi_network/influenza-the-search-for-a-universal-vaccine/article_415b90de-246d-5a05-a69f-a4651c7b4c49.html |
| 2017-12-09 00:30 | http://klewtv.com/news/nation-world/us-flu-season-off-to-an-early-start-widespread-in-7-states-12-08-2017 |
| 2017-12-18 21:15 | https://medicalxpress.com/news/2017-12-flu-vaccine-year-shot.html |
| 2017-12-21 18:30 | https://www.wtvq.com/2017/12/21/flu-activity-now-widespread-kentucky/ |
| 2018-01-12 22:00 | https://patch.com/georgia/smyrna/s/gc0jl/4-dead-from-flu-in-georgia-300-hospitalized |
| 2018-11-09 06:45 | https://www.lewrockwell.com/2018/11/no_author/vitamin-d-vs-flu-shots/ |
| 2018-11-09 18:30 | https://www.chronicleonline.com/news/dragon-boat-festival-veterans-fair-and-free-flu-shots-set/article_9aa5c888-e43b-11e8-930e-ab562e61b2d4.html |
| 2019-01-05 06:45 | https://www.omaha.com/livewellnebraska/health/bad-news-flu-is-on-the-rise-in-omaha-area/article_666258aa-22eb-5086-9255-9343f589f79c.html |
| 2019-01-09 19:15 | http://www.kokomotribune.com/indiana/news/so-far-vigo-doing-well-with-flu-season/article_ff37c511-a4fb-55b5-b008-d3feec7d732c.html |
| 2019-12-08 22:30 | https://1360kmjm.iheart.com/content/2019-12-08-early-flu-season-see-half-the-country-with-high-to-moderate-flu-activity/ |
| 2019-12-13 15:15 | https://www.indystar.com/story/news/health/2019/12/13/norovirus-outbreak-stomach-flu-terrorizes-washington-public-schools/4417867002/ |
| 2019-12-24 14:00 | https://www.wrcbtv.com/story/41491009/tennessee-county-clinics-offering-free-flu-vaccinations |
| 2022-10-21 08:30 | https://www.naturalnews.com/2022-10-20-bird-flu-food-inflation-push-turkey-prices.html |
| 2022-10-31 20:45 | https://www.wvtm13.com/article/flu-cases-are-high-across-central-alabama-right-now/41820285 |
| 2023-12-20 15:45 | https://www.komu.com/news/covid19/new-covid-subvariant-flu-and-rsv-cases-are-rising-a-doctor-explains-how-to-stay/article_69e1210b-f635-592e-a880-da66fce9ad35.html |
| 2024-01-11 15:30 | https://www.squamishchief.com/highlights/record-number-of-hospitalizations-as-covid-and-flu-season-peaks-8093281 |

## AUS (10451 total matched articles; 20 sampled)

| Stamp (GDELT snapshot, UTC) | URL |
|---|---|
| 2016-04-21 14:00 | http://www.portlincolntimes.com.au/story/3863074/now-is-the-time-to-be-washing-your-hands-of-the-flu-threat/?cs=4149 |
| 2016-06-21 05:45 | http://www.mudgeeguardian.com.au/story/3982295/qa-recap-host-tony-jones-puts-flu-ridden-malcolm-turnbull-in-the-hot-seat/ |
| 2017-11-30 12:00 | https://www.pr-inside.com/growing-at-a-cagr-of-8-54-influenza-market-r4662522.htm |
| 2017-12-06 09:30 | http://www.westernadvocate.com.au/story/5104040/big-queues-in-bathurst-hospitals-ed-due-to-record-flu-season/ |
| 2017-12-15 02:15 | https://www.fox4now.com/news/health/flu-season-soars-in-the-united-states-higher-than-usual-for-this-time-of-year |
| 2018-01-10 16:15 | https://www.standard.co.uk/news/uk/strain-of-japanese-flu-that-particularly-affects-children-spreads-across-britain-a3736686.html |
| 2018-01-12 23:00 | https://uk.reuters.com/article/us-usa-influenza/flu-in-u-s-now-widespread-but-season-may-be-peaking-cdc-idUKKBN1F12DT |
| 2018-01-13 00:00 | https://www.statnews.com/2018/01/12/flu-season-cdc/ |
| 2018-01-18 15:15 | http://www.telegraph.co.uk/news/2018/01/18/flu-epidemic-set-hit-britain-within-fortnight-83-million-now/ |
| 2018-01-19 11:00 | http://www.huffingtonpost.co.uk/entry/uk-witnessing-worst-flu-season-since-2011-but-still-not-an-epidemic_uk_5a61b407e4b01d91b2547ab5 |
| 2018-01-27 15:15 | http://wcfcourier.com/news/national/analysis-how-scared-should-you-be-of-the-flu-four/article_967752bd-41c4-5bb3-aefc-6d392809a8b6.html |
| 2018-02-05 17:30 | http://www.dailymail.co.uk/health/article-5354083/Indiana-girl-7-dies-flu-left-hospital.html |
| 2022-03-19 09:15 | https://www.smh.com.au/national/it-s-really-dangerous-now-australia-s-influenza-hiatus-set-to-end-20220318-p5a5w7.html |
| 2022-05-06 11:15 | https://www.smh.com.au/national/queensland/seq-university-trials-new-flu-vaccine-using-cell-based-technology-20220505-p5airu.html |
| 2022-05-16 20:30 | https://www.cairnspost.com.au/news/victoria/50-kids-contract-flu-at-one-melbourne-birthday-party/news-story/d9b731457b831a56dc50a23d2c629312&memtype=anonymous&mode=premium&nk=b97d3e49b50a5e48beb3cc88f649d4bd-1652732243 |
| 2024-04-02 21:15 | https://www.sbs.com.au/news/podcast-episode/new-flu-vaccine-launched-with-flu-season-about-to-start/kwgnzk88h |
| 2024-04-23 02:30 | https://www.manningrivertimes.com.au/story/8602050/spike-in-early-flu-cases-in-nsw-prompts-vaccination-push/?cs=9397 |
| 2024-04-23 03:45 | https://www.boorowanewsonline.com.au/story/8602050/spike-in-early-flu-cases-in-nsw-prompts-vaccination-push/?cs=3031 |
| 2024-04-23 04:15 | https://www.grenfellrecord.com.au/story/8602050/spike-in-early-flu-cases-in-nsw-prompts-vaccination-push/?cs=9676 |
| 2024-06-04 06:15 | https://www.southernhighlandnews.com.au/story/8651791/deadly-avian-influenza-outbreak-spreads-to-third-farm/?cs=9676 |

## IND (4255 total matched articles; 20 sampled)

| Stamp (GDELT snapshot, UTC) | URL |
|---|---|
| 2015-12-19 00:45 | http://www.tribuneindia.com/news/ludhiana/3-more-suspected-swine-flu-cases-reported-in-city/172286.html |
| 2016-01-24 17:15 | http://dunyanews.tv/en/Pakistan/318998-LHC-summons-swine-flu-report-from-govt-health-dep |
| 2017-01-15 13:45 | http://www.vishwagujarat.com/gujarat/ahmedabad-memnagar-declared-bird-flu-hit/ |
| 2017-11-03 15:15 | http://zeenews.india.com/health/new-flu-shot-may-protect-you-lifelong-2054103 |
| 2018-01-03 15:00 | http://english.sakshi.com/news/2018/01/03/bird-flu-fears-grip-bengaluru |
| 2018-01-08 20:45 | https://timesofindia.indiatimes.com/city/bengaluru/avian-flu-942-birds-culled-surveillance-to-continue/articleshow/62420743.cms |
| 2018-11-27 18:45 | https://empowerednews.net/influenza-vaccine-market-professional-and-in-depth-industry-analysis-2018-by-top-key-players-gsk-sinovac-changsheng-ccbio-aleph-biomedical-sanofi-lanzhou-institute-of-biological-produc/181376587/ |
| 2018-12-21 17:00 | https://www.timminstimes.com/news/canada/a-frightful-plague-rampant-all-over-the-world-the-forgotten-horrors-of-the-spanish-influenza/wcm/e8a5a160-7647-4ff5-9fda-dd103e674f62 |
| 2018-12-28 12:45 | https://www.independent.co.uk/news/world/americas/us-border-guatemala-boy-migrant-dies-how-flu-felipe-gomez-alonzo-a8701586.html |
| 2019-01-06 13:45 | https://news.biharprabha.com/2019/01/heres-how-influenza-infection-weakens-ones-body/ |
| 2019-12-23 04:00 | https://www.patnadaily.com/index.php/news/14044-bird-flu-epidemic-at-patna-zoo-two-more-peacocks-die.html |
| 2020-01-30 05:15 | https://timesofindia.indiatimes.com/city/noida/seasons-first-swine-flu-case-in-noida/articleshow/73746251.cms |
| 2020-02-03 04:00 | http://theeconomiccollapseblog.com/archives/4-plagues-are-marching-across-asia-simultaneously-coronavirus-african-swine-fever-h5n1-bird-flu-and-h1n1-swine-flu |
| 2021-07-20 22:00 | https://timesofindia.indiatimes.com/city/delhi/12-year-old-boy-suffering-from-bird-flu-dies-at-aiims-in-delhi/articleshow/84593681.cms |
| 2021-07-24 01:00 | https://bangaloremirror.indiatimes.com/bangalore/cover-story/one-flu-over-the-cuckoos-nest/articleshow/84696168.cms |
| 2022-05-17 08:30 | https://www.nbclosangeles.com/news/national-international/conspiracy-theorists-flock-to-bird-flu-spreading-falsehoods/2895129/ |
| 2024-05-22 06:00 | https://www.theadvocate.com.au/story/8637577/australias-first-human-case-of-bird-flu-detected-in-victoria/?cs=2605 |
| 2024-05-23 14:00 | https://www.armidaleexpress.com.au/story/8638822/bird-flu-at-second-farm-as-farmers-on-high-alert/?cs=9676 |
| 2024-05-23 14:30 | https://www.muswellbrookchronicle.com.au/story/8638822/bird-flu-at-second-farm-as-farmers-on-high-alert/?cs=9676 |
| 2024-06-12 13:30 | https://www.sb.by/en/who-confirmed-case-of-human-infection-with-bird-flu-in-india.html |

## BRA (593 total matched articles; 20 sampled)

| Stamp (GDELT snapshot, UTC) | URL |
|---|---|
| 2015-12-27 20:45 | http://www.wsvn.com/story/30835373/young-girl-recovers-after-flu-nearly-kills-her |
| 2016-01-04 15:30 | http://demerarawaves.com/2016/01/04/health-care-workers-who-treated-swine-flu-victim-vaccinated/ |
| 2016-11-24 22:15 | http://www.prnewswire.com/news-releases/global-influenza-vaccines-market-and-forecast-to-2021---size-share-growth-and-trends-analysis-300368573.html |
| 2016-11-29 12:15 | http://health.asiaone.com/health/health-news/s-korea-cull-3-percent-poultry-contain-bird-flu |
| 2017-01-30 10:00 | https://www.bloomberg.com/news/articles/2017-01-30/growing-hunger-for-brazilian-chicken-as-bird-flu-crisis-spreads-iyjbxsms |
| 2017-10-30 22:15 | https://www.moneytalksnews.com/6-low-cost-ways-to-keep-the-flu-at-bay/ |
| 2019-11-29 13:15 | https://www.marketwatch.com/press-release/global-influenza-diagnostics-market-may-see-a-growth-rate-of-686-and-would-reach-the-market-size-of-usd92314-million-by-2024-2019-11-29 |
| 2021-12-12 08:30 | https://www.news24.com/fin24/economy/bird-flu-is-raging-adding-to-the-risks-for-food-inflation-20211211 |
| 2022-01-04 17:30 | https://www.washingtonpost.com/world/2022/01/04/twindemic-coronavirus-flu-outbreak-2021-israel-brazil-australia/ |
| 2022-01-05 23:45 | https://www.fox6now.com/news/flurona-what-you-need-to-know-about-the-flu-covid-19-dual-illness |
| 2023-01-27 18:45 | https://finance.yahoo.com/news/influenza-diagnostics-market-worth-usd-180000947.html |
| 2023-02-17 11:45 | https://www.theepochtimes.com/bird-flu-continues-to-spread-worldwide-threatening-poultry-supplies_5061683.html |
| 2023-02-17 17:30 | https://www.foxnews.com/world/global-bird-flu-alarm-prompts-countries-reconsider-once-shunned-vaccines |
| 2023-02-17 18:00 | https://www.nbcnews.com/science/science-news/bird-flu-alarm-drives-world-shunned-vaccines-rcna71213 |
| 2023-02-20 00:45 | https://www.globenewswire.com/news-release/2023/02/19/2611074/0/en/Clover-Enters-into-Exclusive-Agreement-to-Commercialize-Quadrivalent-Seasonal-Influenza-Vaccine-in-Mainland-China.html |
| 2023-02-21 17:45 | https://www.londonmercury.com/news/273550933/no-end-in-sight-as-us-bird-flu-outbreak-enters-year-two |
| 2023-03-15 21:00 | https://www.cidrap.umn.edu/avian-influenza-bird-flu/study-h5n1-avian-flu-seal-deaths-reveals-multiple-lineages |
| 2023-03-23 22:45 | https://www.cidrap.umn.edu/avian-influenza-bird-flu/study-h5n1-avian-flu-seal-deaths-reveals-multiple-lineages |
| 2023-12-12 20:15 | https://www.postcourier.com.pg/bird-flu-kills-seals-sea-lions/ |
| 2024-01-02 22:30 | https://www.marketscreener.com/news/latest/Brazil-Mexico-eye-regional-avian-flu-plan-to-keep-trade-flowing-45661389/ |

## IDN (216 total matched articles; 20 sampled)

| Stamp (GDELT snapshot, UTC) | URL |
|---|---|
| 2015-11-07 18:30 | http://www.sott.net/article/305846-The-Health-and-Wellness-Show-Vaccines-and-Flu-Shots |
| 2016-01-15 01:15 | http://quadrangleonline.com/2016/01/15/a-late-start-to-the-flu-season/ |
| 2016-11-24 22:15 | http://www.prnewswire.com/news-releases/global-influenza-vaccines-market-and-forecast-to-2021---size-share-growth-and-trends-analysis-300368573.html |
| 2016-11-27 10:00 | http://www.antaranews.com/en/news/108059/dutch-destroy-190000-ducks-in-first-bird-flu-cull |
| 2016-11-28 23:15 | http://www.agcanada.com/cns_feed/feed-grains-bird-flu-outbreaks-watched |
| 2016-12-07 11:00 | https://wn.com/my_response_-_bird_flu_chicken_farm_cull_begins_at_craigies_poultry_farm |
| 2016-12-17 21:45 | http://www.prnewswire.com/news-releases/asia-and-australasia-influenza-vaccines-market-persons-vaccinated-brand-analysis-and-forecast-to-2021-300380475.html |
| 2016-12-17 21:45 | http://finance.yahoo.com/news/asia-australasia-influenza-vaccines-market-211600965.html |
| 2016-12-18 08:00 | https://au.news.yahoo.com/world/a/33600656/japan-culling-210-000-birds-amid-spreading-avian-flu/ |
| 2016-12-18 12:00 | http://www.antaranews.com/en/news/108470/ireland-urges-poultry-owners-to-remain-vigilant-against-bird-flu |
| 2017-01-06 02:45 | http://sglinks.com/pages/86949888-china-confirms-latest-human-death-from-h7n9-bird-flu-east |
| 2017-11-10 21:45 | https://www.prnewswire.com/news-releases/h5n8-bird-flu-pandemic-now-disruptive-in-south-africa-might-have-been-controlled-by-specific-replikins-vaccines-and-blockers-available-since-2013-300554055.html |
| 2017-11-21 04:00 | http://www.staradvertiser.com/2017/11/20/nyt/bird-flu-is-spreading-in-asia-experts-quietly-warn/ |
| 2019-01-02 20:45 | http://brazilbusiness.einnews.com/pr_news/472672935/global-influenza-vaccines-market-report-2018-persons-vaccinated-brand-analysis-size-share-growth-trends-major-deals-forecast-to-2024 |
| 2021-04-18 20:00 | https://ksusentinel.com/2021/04/18/global-influenza-diagnostics-market-to-amass-massive-roi-over-2021-2026-market-research-store/ |
| 2021-11-19 14:00 | https://en.antaranews.com/news/200453/indonesians-over-60-prioritized-to-receive-influenza-vaccination |
| 2021-11-24 01:30 | https://www.webmd.com/cold-and-flu/flu-guide/what-know-about-bird-flu |
| 2021-12-26 19:00 | https://www.france24.com/en/live-news/20211226-large-israel-bird-flu-outbreak-kills-2-000-wild-cranes |
| 2022-12-06 14:00 | https://www.jacksonprogress-argus.com/news/5-things-to-know-for-dec-6-georgia-runoff-hawaii-volcano-scotus-flu-ukraine/article_ed5656d7-cec2-5049-a19e-4804b50d8fdb.html |
| 2022-12-27 19:00 | https://www.parisguardian.com/news/273275559/for-second-week-us-reports-declining-cases-of-flu |

## KEN (163 total matched articles; 20 sampled)

| Stamp (GDELT snapshot, UTC) | URL |
|---|---|
| 2018-01-11 20:15 | https://www.the-star.co.ke/news/2018/01/11/britain-flu-cases-levels-very-high-in-hospitals_c1696964 |
| 2018-01-24 03:30 | https://www.niagarathisweek.com/news-story/8088410-flu-deaths-in-kids-rare-but-do-occur-experts/ |
| 2021-02-20 21:30 | https://www.the-sun.com/news/2374311/russia-worlds-first-human-infection-h5n8-bird-flu/ |
| 2022-04-05 13:00 | https://www.downtoearth.org.in/news/health/covid-19-has-suppressed-influenza-for-now-but-it-will-return-with-greater-severity-study-82228 |
| 2022-05-03 20:30 | https://www.iowapublicradio.org/podcast/talk-of-iowa/2022-05-03/tracking-the-movement-of-bird-flu-through-wildlife-populations |
| 2023-01-06 06:30 | https://www.standardmedia.co.ke/health/article/2001464584/report-flu-diarrhoea-top-nairobi-residents-disease-burden |
| 2024-01-04 00:00 | https://www.ksat.com/health/2024/01/03/more-hospitals-are-requiring-masks-as-flu-and-covid-19-cases-surge/ |
| 2024-01-04 00:00 | https://www.sfgate.com/news/article/more-hospitals-are-requiring-masks-as-flu-and-18588055.php |
| 2024-01-04 01:30 | https://www.myplainview.com/news/article/more-hospitals-are-requiring-masks-as-flu-and-18588055.php |
| 2024-01-04 02:15 | https://www.coastreporter.net/the-mix/more-hospitals-are-requiring-masks-as-flu-and-covid-19-cases-surge-8054450 |
| 2024-01-04 03:45 | https://www.greenwichtime.com/news/article/more-hospitals-are-requiring-masks-as-flu-and-18588055.php |
| 2024-01-04 05:15 | https://www.newspressnow.com/news/national_news/more-hospitals-are-requiring-masks-as-flu-and-covid-19-cases-surge/article_533e96ff-8bc3-5db2-ab32-eecf526a9917.html |
| 2024-01-04 20:45 | https://www.cbs19.tv/article/news/nation-world/hospitals-requiring-masks-as-flu-and-covid-19-cases-surge/507-40a9dc84-58e8-4aa8-9eee-f787bc7b589e |
| 2024-01-04 21:00 | https://www.ncnewsonline.com/news/local_news/more-hospitals-are-requiring-masks-as-flu-and-covid-19-cases-surge/article_c25917a2-9e05-5b90-b92f-7e5be6070b84.html |
| 2024-01-04 23:30 | https://www.wqad.com/article/news/nation-world/hospitals-requiring-masks-as-flu-and-covid-19-cases-surge/507-40a9dc84-58e8-4aa8-9eee-f787bc7b589e |
| 2024-01-04 23:30 | https://www.abc10.com/article/news/nation-world/hospitals-requiring-masks-as-flu-and-covid-19-cases-surge/507-40a9dc84-58e8-4aa8-9eee-f787bc7b589e |
| 2024-01-04 23:45 | https://www.beaumontenterprise.com/news/article/more-hospitals-are-requiring-masks-as-flu-and-18588055.php |
| 2024-01-05 00:00 | https://www.wfmynews2.com/article/news/nation-world/hospitals-requiring-masks-as-flu-and-covid-19-cases-surge/507-40a9dc84-58e8-4aa8-9eee-f787bc7b589e |
| 2024-01-05 02:45 | https://www.9news.com/article/news/nation-world/hospitals-requiring-masks-as-flu-and-covid-19-cases-surge/507-40a9dc84-58e8-4aa8-9eee-f787bc7b589e |
| 2024-01-05 19:00 | https://www.timescolonist.com/coronavirus-covid-19-national-news/more-hospitals-are-requiring-masks-as-flu-and-covid-19-cases-surge-8054534 |
