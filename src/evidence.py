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
