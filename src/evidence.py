"""Where each planner rule comes from.

Every safety check and week-type rule names one or more keys from SOURCES,
so the plan can show the paper behind it - or say plainly when a number
is our own cautious choice rather than a research finding.

DOIs were checked against the papers or their publisher/PubMed records.
"""

SOURCES = {
    "nielsen2014": {
        "cite": "Nielsen et al. 2014, J Orthop Sports Phys Ther 44(10):739-747",
        "doi": "10.2519/jospt.2014.5164",
        "finding": "Novice runners: >30% increase over 2 weeks linked to more distance-related "
                   "injuries (HR 1.59, p = .07); 10-30% no riskier than <10%.",
    },
    "buist2008": {
        "cite": "Buist et al. 2008, Am J Sports Med 36(1):33-39",
        "doi": "10.1177/0363546507307505",
        "finding": "Randomised trial: a graded 10%-rule programme did not reduce injuries in novice runners.",
    },
    "cloosterman2024": {
        "cite": "Cloosterman et al. 2024, J Athl Train 59(10):1028-1034",
        "doi": "10.4085/1062-6050-0430.23",
        "finding": "Different acute:chronic methods flag different weeks; no method is validated for runners. "
                   "1.5 is the usual 'high' cut-off.",
    },
    "windt2019": {
        "cite": "Windt & Gabbett 2019, Br J Sports Med 53(16):988-990",
        "doi": "10.1136/bjsports-2017-098925",
        "finding": "Including the current week in the chronic average (coupling) biases the ratio.",
    },
    "fokkema2020": {
        "cite": "Fokkema et al. 2020, Scand J Med Sci Sports 30(9):1692-1704",
        "doi": "10.1111/sms.13725",
        "finding": "Longer long runs and >32 km/week linked to faster half-marathon times, not to more injuries; "
                   "a previous injury in the last 12 months was the strongest injury predictor.",
    },
    "rosenblat2025": {
        "cite": "Rosenblat et al. 2025, Sports Med 55:655-673",
        "doi": "10.1007/s40279-024-02149-3",
        "finding": "Polarized and pyramidal training perform about the same; mostly-easy training with some "
                   "moderate (tempo) work suits recreational runners.",
    },
    "hodgson2022": {
        "cite": "Hodgson et al. 2022, Sci Total Environ 842:156825",
        "doi": "10.1016/j.scitotenv.2022.156825",
        "finding": "The slowest finishers lost the most time per extra degree C; elite runners were barely affected.",
    },
    "tanaka2001": {
        "cite": "Tanaka et al. 2001, J Am Coll Cardiol 37(1):153-156",
        "doi": "10.1016/s0735-1097(00)01054-8",
        "finding": "Max HR = 208 - 0.7 x age on average, but individuals vary by about 10 bpm (SD), "
                   "so a directly measured max HR should be used whenever possible.",
    },
    "sartor2018": {
        "cite": "Sartor et al. 2018, BMC Sports Sci Med Rehabil 10:10",
        "doi": "10.1186/s13102-018-0098-0",
        "finding": "Wrist optical HR vs chest strap while running: mean error 2 bpm, limits of agreement "
                   "about +/-14 bpm. Measuring max HR needs <=3 bpm error; training targets <8 bpm. "
                   "(Philips prototype, not Garmin; authors are Philips employees.)",
    },
    "wang2025": {
        "cite": "Wang et al. 2025, Sports Med Open 11:22",
        "doi": "10.1186/s40798-025-00824-x",
        "finding": "36 recreational runners: strength, gait and joint mechanics recovered within 1 day of a "
                   "half marathon, hip position sense within 2 days. Authors advise no higher-intensity "
                   "activity for 2 days.",
    },
    "zhou2026": {
        "cite": "Zhou et al. 2026, BMC Sports Sci Med Rehabil 18:192",
        "doi": "10.1186/s13102-026-01640-w",
        "finding": "24 amateur runners randomised after a half marathon: with rest, thigh muscle microdamage "
                   "(MRI) was back to baseline at 72 h; 30 min/day of moderate or hard running from 24 h "
                   "delayed or prevented recovery. Advises no moderate/hard running for 3 days.",
    },
    "benitez2025": {
        "cite": "Benitez-Munoz et al. 2025, Eur J Appl Physiol 125:499-510",
        "doi": "10.1007/s00421-024-05622-z",
        "finding": "First ventilatory threshold (top of 'easy') at 74.6% (men) / 77.9% (women) of max HR "
                   "in the lowest training group, higher in fitter people, SD about 5-7%: a fixed "
                   "percentage of max HR fits individuals poorly.",
    },
    "racinais2015": {
        "cite": "Racinais et al. 2015, Scand J Med Sci Sports 25(Suppl 1):6-19",
        "doi": "10.1111/sms.12467",
        "finding": "Heat consensus: acclimatise over 1-2 weeks; for exercise over 1 h take 0.5-0.7 g/L "
                   "sodium and 30-60 g/h carbohydrate (up to 90 g/h beyond 2.5 h); slower recreational "
                   "runners should avoid over-drinking.",
    },
    "casado2022": {
        "cite": "Casado et al. 2022, Int J Sports Physiol Perform 17:820-833",
        "doi": "10.1123/ijspp.2021-0435",
        "finding": "Elite distance runners train mostly easy (pyramidal), with regular threshold (tempo) "
                   "and interval sessions and at least 3 easy days a week.",
    },
    "bosquet2007": {
        "cite": "Bosquet et al. 2007, Med Sci Sports Exerc 39(8):1358-1365",
        "doi": "10.1249/mss.0b013e31806010e0",
        "finding": "Taper meta-analysis: about 2 weeks, training volume cut 41-60%, intensity and "
                   "frequency kept, gave the largest performance gains (competitive athletes).",
    },
    "riegel1981": {
        "cite": "Riegel 1981, American Scientist 69:285-290",
        "doi": None,
        "finding": "Race time scales with distance as T2 = T1 x (D2 / D1)^1.06 across endurance events.",
    },
    "nuuttila2025": {
        "cite": "Nuuttila et al. 2025, Eur J Appl Physiol 125:2161-2171",
        "doi": "10.1007/s00421-025-05748-8",
        "finding": "165 recreational runners, lab lactate tests: the first lactate threshold (top of 'easy') "
                   "was at 78.9% (men) / 83.6% (women) of measured max HR, SD about 4-5%. At 80% of max HR, "
                   "43% of runners were already above it; <=70% keeps almost everyone easy.",
    },
    "sandbakk2025": {
        "cite": "Sandbakk et al. 2025, Sports Med Open 11:45",
        "doi": "10.1186/s40798-025-00848-3",
        "finding": "12 world-class Norwegian endurance coaches: mostly low-intensity training, 2-3 hard days "
                   "a week, an easier week every 3-4 weeks (1-2 fewer sessions, 25-35% less volume); "
                   "tapers keep frequency and shorten sessions. Elite athletes, coaches' accounts.",
    },
    "filipas2022": {
        "cite": "Filipas et al. 2022, Scand J Med Sci Sports 32:498-511",
        "doi": "10.1111/sms.14101",
        "finding": "60 well-trained runners, 16 weeks of 3 hard + 1 easier week (-30 to -40%): all groups "
                   "improved 5 km; tempo-heavy (pyramidal) first, then interval-heavy (polarized) improved "
                   "most (-1.5%), though below the test's smallest detectable change.",
    },
    "boullosa2020": {
        "cite": "Boullosa et al. 2020, Sports 8(3):35",
        "doi": "10.3390/sports8030035",
        "finding": "Review for recreational runners: 1-2 high-intensity sessions a week with >=75% of volume "
                   "easy, 1-2 strength sessions a week; weekly distance is the main injury factor; the "
                   "'10% rule' is anecdotal, without robust support.",
    },
    "nuuttila2022ind": {
        "cite": "Nuuttila et al. 2022, Med Sci Sports Exerc 54(10):1690-1701",
        "doi": "10.1249/MSS.0000000000002968",
        "finding": "30 recreational runners: volume +10% of baseline per hard week, every 3rd week -25%. "
                   "Adjusting load twice a week from recovery and the heart rate-running speed index "
                   "improved 10 km more (-6.2% vs -2.9% over 12 weeks) and left fewer low responders.",
    },
    "nuuttila2022block": {
        "cite": "Nuuttila et al. 2022, Med Sci Sports Exerc 54(5):851-860",
        "doi": "10.1249/MSS.0000000000002861",
        "finding": "30 recreational runners, 2 weeks of either 5 interval sessions a week or +70% easy "
                   "volume: both improved 3000 m about 2%, but the interval block raised muscle soreness and "
                   "lowered readiness to train; more soreness and fatigue went with smaller gains.",
    },
    "suwankan2024": {
        "cite": "Suwankan et al. 2024, J Hum Sport Exerc 19(1):193-201",
        "doi": "10.14198/jhse.2024.191.17",
        "finding": "60 Thai recreational runners: weekly distance predicted 10 km time best, then race "
                   "experience, training days and years running (57% explained). Runners at 56-80 min "
                   "mostly ran 30-59 km/week on 4-5 days. Cross-sectional.",
    },
    "vickers2016": {
        "cite": "Vickers & Vertosick 2016, BMC Sports Sci Med Rehabil 8:26",
        "doi": "10.1186/s13102-016-0052-y",
        "finding": "2,303 recreational runners: Riegel predicted well up to the half marathon but the "
                   "marathon too fast (10+ min for half of runners, even with 1.08). Tempo runs went "
                   "with ~6-7% faster 10 km, intervals ~2-4%, more weekly distance faster at every distance.",
    },
    "zoladz2021": {
        "cite": "Zoladz & Nieckarz 2021, PeerJ 9:e11562",
        "doi": "10.7717/peerj.11562",
        "finding": "Model: running breathes 62-115 L/min vs 8 L/min at rest, so an hour of running at "
                   "PM10 50 ug/m3 deposits as much as an hour of rest at 251-466 ug/m3 (5-9x the rate).",
    },
    "havenga2026": {
        "cite": "Havenga et al. 2026, Int J Environ Health Res 36(7):1866-1874",
        "doi": "10.1080/09603123.2025.2605164",
        "finding": "PM2.5 at athletics meets 29-133 ug/m3, with 1-minute spikes to 385 near industry and "
                   "smoke from food stalls. No short-term PM2.5 limit for exercise exists; WHO's 24-hour "
                   "guideline (15 ug/m3) assumes resting breathing.",
    },
    "zhu2021": {
        "cite": "Zhu et al. 2021, Sci Rep 11:19249",
        "doi": "10.1038/s41598-021-98844-6",
        "finding": "368 adults walking a busy road in Xi'an: heart rate rose with PM2.5 and risk thresholds "
                   "fell between 81 and 168 ug/m3, lower for middle-aged people and BMI outside 18.5-24. "
                   "Walking, not running; risk partly self-reported.",
    },
    "munoz2014": {
        "cite": "Muñoz et al. 2014, Int J Sports Physiol Perform 9:265-272",
        "doi": "10.1123/IJSPP.2012-0350",
        "finding": "30 recreational runners (10K ~39 min), 10 weeks, 5-6 runs and 2 hard sessions a week: "
                   "~77% of time below the first threshold (achieved 73%) vs ~46% both improved 10K (5.0% vs "
                   "3.6%, not significant); the 6 who kept 78% easy improved 7.0% vs 1.6% for the 6 who kept "
                   "32% (d = 1.29). Many runners did not keep to the prescribed intensities.",
    },
    "nielsen2020": {
        "cite": "Nielsen et al. 2020, Br J Sports Med 54(1):51-57",
        "doi": "10.1136/bjsports-2019-100858",
        "finding": "A session counts as done within +/-10% of its prescribed distance or time. In 4 trials of "
                   "running programmes (56-839 runners, 4-24 weeks) only 0-21% did every session that way; "
                   "the authors ask for an 'acceptable threshold' set in advance but give no number.",
    },
    "own": {
        "cite": "Planner default",
        "doi": None,
        "finding": "A cautious number chosen for this planner, not taken from a study.",
    },
}


def describe(keys):
    """'Nielsen et al. 2014 (doi:...); Planner default' for display."""
    parts = []
    for key in keys:
        source = SOURCES[key]
        parts.append(f"{source['cite']} (doi:{source['doi']})" if source["doi"] else source["cite"])
    return "; ".join(parts)
