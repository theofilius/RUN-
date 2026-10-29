"""Dashboard text in English and Indonesian.

Every sentence the dashboard shows is here, keyed by name, with {placeholders}
for numbers. The planner returns data (week type, reasons, check results), and
the dashboard words it with these texts, so both languages say the same thing.

The detailed technical notes from src/ (formulas, sources) stay in English.
"""

LANGUAGES = {"id": "Indonesia", "en": "English"}

DAYS = {"en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "id": ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]}
DAYS_LONG = {"en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
             "id": ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]}
MONTHS = {"en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
          "id": ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]}

TEXT = {
    # ---- header and data ----
    "tagline": ("Garmin records your runs. This explains your training.",
                "Garmin merekam larimu. Aplikasi ini menjelaskan latihanmu."),
    "data source": ("Data source", "Sumber data"),
    "garmin source": ("Garmin Connect (synced)", "Garmin Connect (sinkron)"),
    "sync now": ("Sync now", "Sinkronkan"),
    "syncing": ("Syncing with Garmin Connect...", "Sinkron dengan Garmin Connect..."),
    "downloading": ("Downloading activity files {done}/{total}", "Mengunduh file aktivitas {done}/{total}"),
    "reading runs": ("Reading your runs (new activity files take a few seconds each)...",
                     "Membaca data lari (file aktivitas baru butuh beberapa detik per file)..."),
    "synced": ("Synced {when} · {runs} runs since {since}", "Sinkron {when} · {runs} lari sejak {since}"),
    "new activities": ("{n} new activities from Garmin", "{n} aktivitas baru dari Garmin"),
    "sync failed": ("Garmin sync failed ({error}). Showing the last synced data.",
                    "Sinkron Garmin gagal ({error}). Yang tampil adalah data sinkron terakhir."),
    "key rejected": ("Garmin rejected the API key - it may have expired or been revoked. Create a new one on "
                     "Garmin Connect web (Settings → Personal API Token) and replace GARMIN_API_KEY in .env.",
                     "Garmin menolak API key - mungkin sudah habis atau dicabut. Buat yang baru di Garmin "
                     "Connect web (Settings → Personal API Token), lalu ganti GARMIN_API_KEY di .env."),
    "key expires": ("Your Garmin API key expires in {days} days. Create a new one on Garmin Connect web "
                    "(Settings → Personal API Token), then update GARMIN_API_KEY and GARMIN_API_KEY_EXPIRES in .env.",
                    "API key Garmin-mu habis dalam {days} hari. Buat yang baru di Garmin Connect web "
                    "(Settings → Personal API Token), lalu ganti GARMIN_API_KEY dan GARMIN_API_KEY_EXPIRES di .env."),
    "key expired": ("Your Garmin API key has expired. Create a new one on Garmin Connect web "
                    "(Settings → Personal API Token), then update GARMIN_API_KEY and GARMIN_API_KEY_EXPIRES in .env.",
                    "API key Garmin-mu sudah habis. Buat yang baru di Garmin Connect web "
                    "(Settings → Personal API Token), lalu ganti GARMIN_API_KEY dan GARMIN_API_KEY_EXPIRES di .env."),
    "no data": ("No data yet. Put GARMIN_API_KEY in .env, or export a Garmin CSV into {folder}.",
                "Belum ada data. Isi GARMIN_API_KEY di .env, atau taruh export CSV Garmin di {folder}."),

    # ---- names ----
    "kind easy": ("Easy run", "Easy run"),
    "kind long": ("Long run", "Long run"),
    "kind tempo": ("Tempo run", "Tempo run"),
    "kind interval": ("Intervals", "Interval"),
    "kind rest": ("Rest", "Istirahat"),
    "kind race": ("Race", "Race"),
    "short easy": ("Easy", "Easy"),
    "short long": ("Long", "Long"),
    "short tempo": ("Tempo", "Tempo"),
    "short interval": ("Interval", "Interval"),
    "short rest": ("Rest", "Libur"),
    "short race": ("Race", "Race"),
    "week recovery": ("Recovery", "Pemulihan"),
    "week fix easy": ("Easy first", "Fokus santai"),
    "week build": ("Build", "Membangun"),
    "week step back": ("Lighter week", "Minggu ringan"),
    "week taper": ("Taper", "Taper"),
    "week race week": ("Race week", "Minggu race"),
    "step warm-up": ("Warm-up", "Pemanasan"),
    "step easy": ("Easy", "Santai"),
    "step tempo": ("Tempo", "Tempo"),
    "step interval": ("Fast", "Cepat"),
    "step recovery": ("Jog", "Jogging"),
    "step race pace": ("Goal pace", "Pace target"),
    "step cool-down": ("Cool-down", "Pendinginan"),

    # ---- today ----
    "week n": ("Week {n}", "Minggu {n}"),
    "stat distance": ("distance", "jarak"),
    "stat hr": ("heart rate", "detak jantung"),
    "stat pace tempo": ("tempo pace", "pace tempo"),
    "stat pace reps": ("pace per repeat", "pace tiap repetisi"),
    "stat time": ("about", "perkiraan waktu"),
    "min short": ("min", "mnt"),
    "hint hr": ("Roughly {fast}–{slow} /km. Follow heart rate, not pace: walk a minute if it climbs above the range.",
                "Kira-kira {fast}–{slow} /km. Ikuti detak jantung, bukan pace: jalan semenit kalau naik melewati batas."),
    "hint interval": ("{reps} repeats of 800 m, with a 400 m slow jog between. Same pace every repeat.",
                      "{reps} repetisi 800 m, jogging pelan 400 m di antaranya. Pace sama di setiap repetisi."),
    "hint tempo": ("The red part ({km} km) is comfortably hard: short phrases, not full sentences.",
                   "Bagian merah ({km} km) agak berat tapi terkendali: masih bisa bicara pendek, bukan kalimat panjang."),
    "about min": ("about {min} min", "sekitar {min} menit"),
    "keep hr": ("Keep your heart rate at <b>{lo}–{hi}</b>", "Jaga detak jantung di <b>{lo}–{hi}</b>"),
    "pace hint": ("roughly {fast}–{slow} /km - follow heart rate, not pace",
                  "kira-kira {fast}–{slow} /km - ikuti detak jantung, bukan pace"),
    "tempo main": ("Main part: <b>{km} km at {fast}–{slow} /km</b>", "Bagian inti: <b>{km} km di {fast}–{slow} /km</b>"),
    "tempo main hr": ("Main part: <b>{km} km at heart rate {lo}–{hi}</b>",
                      "Bagian inti: <b>{km} km di detak jantung {lo}–{hi}</b>"),
    "interval main": ("<b>{reps} × 800 m at {fast}–{slow} /km</b>, 400 m slow jog between",
                      "<b>{reps} × 800 m di {fast}–{slow} /km</b>, jogging pelan 400 m di antaranya"),
    "strides": ("After the easy part: 6 × 20 s strides - quick but relaxed, not a sprint.",
                "Setelah bagian santai: 6 × 20 detik strides - cepat tapi rileks, bukan sprint."),
    "finish": ("The last {km} km before the cool-down at goal pace {pace}/km.",
               "{km} km terakhir sebelum pendinginan di pace target {pace}/km."),
    "fuel": ("Over an hour: bring water with electrolytes and 30-60 g carbs per hour.",
             "Lebih dari sejam: bawa air plus elektrolit dan 30-60 g karbohidrat per jam."),
    "rest before plan": ("Your plan has not started yet.", "Plan-mu belum dimulai."),
    "rest post race": ("Rest day {day} after your race: muscles need about 72 hours. Walking is fine.",
                       "Hari ke-{day} setelah race: otot butuh sekitar 72 jam untuk pulih. Jalan kaki boleh."),
    "rest after long": ("Rest after yesterday's long run. A light walk or stretching is fine.",
                        "Istirahat setelah long run kemarin. Jalan santai atau stretching boleh."),
    "rest after tempo": ("Rest after yesterday's tempo run. A light walk or stretching is fine.",
                         "Istirahat setelah tempo run kemarin. Jalan santai atau stretching boleh."),
    "rest normal": ("Rest. Optional: a walk, stretching or 15-20 min of strength (squats, lunges, calf raises).",
                    "Istirahat. Kalau mau: jalan kaki, stretching, atau 15-20 menit latihan kekuatan "
                    "(squat, lunge, calf raise)."),
    "rest before race": ("Rest before the race: a short walk, lay out your kit, eat and sleep well.",
                         "Istirahat sebelum race: jalan sebentar, siapkan perlengkapan, makan dan tidur yang cukup."),
    "race day": ("Race day: {name}. Start easy, drink and fuel early.",
                 "Hari race: {name}. Mulai pelan, minum dan isi energi sejak awal."),
    "next up": ("Next: {day} - {kind} {km} km", "Berikutnya: {day} - {kind} {km} km"),
    "done today": ("Done: {km} km at an average heart rate of {hr}.",
                   "Sudah lari: {km} km, detak jantung rata-rata {hr}."),
    "weather at": ("{start}-{end}: {sky}{temp}°C, rain {rain}%", "{start}-{end}: {sky}{temp}°C, hujan {rain}%"),
    "air bad": ("Air is unhealthy (AQI {aqi}) - a treadmill or a shorter run is wiser today.",
                "Udara tidak sehat (AQI {aqi}) - lebih baik treadmill atau lari lebih pendek hari ini."),
    "air sensitive": ("Air is not great (AQI {aqi}) - pick a cleaner hour if you can.",
                      "Udara kurang bagus (AQI {aqi}) - pilih jam yang lebih bersih kalau bisa."),
    "why": ("Why this plan?", "Kenapa begini?"),
    "technical": ("Technical details", "Detail teknis (bahasa Inggris)"),

    # ---- week reasons ----
    "why recovery": ("You raced {days} days before this week. After a long race, give it about two weeks of "
                     "easy running: no hard sessions yet.",
                     "Kamu race {days} hari sebelum minggu ini. Setelah race jarak jauh, beri waktu sekitar dua "
                     "minggu lari santai dulu: belum ada sesi keras."),
    "why fix easy": ("Only {pct}% of your recent running was truly easy. First make easy runs easy (heart rate "
                     "under {hr}); harder sessions come after that.",
                     "Baru {pct}% larimu belakangan ini yang benar-benar santai. Rapikan dulu lari santainya "
                     "(detak jantung di bawah {hr}); sesi keras menyusul setelah itu."),
    "why build": ("Your easy running is under control, so one harder session a week is added - tempo and "
                  "intervals take turns.",
                  "Lari santaimu sudah terkendali, jadi ada satu sesi lebih keras per minggu - tempo dan "
                  "interval bergantian."),
    "why step back": ("Every 4th week is lighter, so your body can absorb the work of the weeks before.",
                      "Setiap minggu ke-4 dibuat lebih ringan supaya tubuh bisa menyerap latihan minggu-minggu "
                      "sebelumnya."),
    "why taper": ("Two weeks before your race: less distance so you arrive fresh; a little speed is kept.",
                  "Dua minggu sebelum race: jarak dikurangi supaya kamu datang segar; sedikit kecepatan tetap dijaga."),
    "why race week": ("Race week: short and easy, and rest on the two days before.",
                      "Minggu race: pendek dan santai, lalu istirahat dua hari sebelum race."),
    "why runs": ("{n} runs this week. One run is added each week until {target} a week - running more often "
                 "comes before running longer.",
                 "{n} lari minggu ini. Tiap minggu ditambah satu lari sampai {target} per minggu - lebih sering "
                 "dulu, baru lebih jauh."),
    "why runs full": ("{n} runs this week - your target number of runs.",
                      "{n} lari minggu ini - sudah sesuai target jumlah lari."),
    "why long": ("Long run {km} km. It grows 1 km a week when you finished last week's.",
                 "Long run {km} km. Naik 1 km per minggu kalau long run minggu lalu selesai."),
    "frozen": ("Locked: this is the plan as you saw it during the week (saved {when}).",
               "Terkunci: ini plan seperti yang kamu lihat selama minggu itu (disimpan {when})."),

    # ---- this week ----
    "this week": ("This week", "Minggu ini"),
    "week summary": ("{km} km in {n} runs · long run {long} km", "{km} km dalam {n} lari · long run {long} km"),
    "state done": ("done", "selesai"),
    "state missed": ("missed", "terlewat"),
    "state today": ("today", "hari ini"),
    "state extra": ("extra run", "lari tambahan"),
    "day menus": ("Every day's menu", "Menu tiap hari"),
    "col step": ("step", "langkah"),
    "col hr": ("heart rate", "detak jantung"),
    "col pace": ("pace", "pace"),
    "col time": ("time", "waktu"),
    "col how": ("how", "cara"),
    "note warm-up": ("3-5 min brisk walk, then a very gentle jog. Walk if heart rate passes {hr}.",
                     "Jalan cepat 3-5 menit, lalu jogging sangat pelan. Jalan kalau detak jantung lewat {hr}."),
    "note warm-up strides": ("3-5 min brisk walk, then a very gentle jog. Finish with 4 × 20 s relaxed strides.",
                             "Jalan cepat 3-5 menit, lalu jogging sangat pelan. Tutup dengan 4 × 20 detik strides santai."),
    "note easy": ("Chatting pace. Walk 1 min whenever heart rate passes {hr}.",
                  "Pace ngobrol. Jalan 1 menit setiap detak jantung lewat {hr}."),
    "note easy long": ("Steady and relaxed. Walk 1 min whenever heart rate passes {hr} - walking breaks are fine.",
                       "Stabil dan rileks. Jalan 1 menit setiap detak jantung lewat {hr} - jeda jalan itu wajar."),
    "note tempo": ("Comfortably hard: short phrases, not full sentences. Ease off if heart rate goes above the range.",
                   "Agak berat tapi terkendali: masih bisa bicara pendek, bukan kalimat panjang. Kurangi kalau "
                   "detak jantung lewat batas."),
    "note interval": ("Rep {i} of {n}: hard but controlled, the same pace every rep.",
                      "Repetisi {i} dari {n}: keras tapi terkendali, pace sama setiap repetisi."),
    "note recovery": ("Slow jog or walk until your breathing settles.", "Jogging pelan atau jalan sampai napas tenang."),
    "note race pace": ("The effort you could hold on race day. Stop the block early if it feels hard.",
                       "Usaha yang bisa kamu tahan saat race. Berhenti lebih awal kalau terasa berat."),
    "note cool-down": ("Very gentle jog, then walk. Drink and stretch afterwards.",
                       "Jogging sangat pelan, lalu jalan. Minum dan stretching sesudahnya."),

    # ---- goal ----
    "your goal": ("Your goal", "Target kamu"),
    "distance": ("Distance", "Jarak"),
    "target": ("Target", "Target"),
    "no target": ("No target yet", "Belum ada target"),
    "has date": ("I have a race date", "Sudah ada tanggal race"),
    "race date": ("Race date", "Tanggal race"),
    "dist 5K": ("5K", "5K"), "dist 10K": ("10K", "10K"),
    "dist Half marathon": ("Half marathon", "Half marathon"), "dist Marathon": ("Marathon", "Marathon"),
    "mark a race": ("Mark a past race (Event Type: Race in Garmin Connect) to get target options.",
                    "Tandai race yang sudah lewat (Event Type: Race di Garmin Connect) supaya pilihan target muncul."),
    "pick target": ("Pick a target: the plan then sets how much you build up to and adds goal-pace practice.",
                    "Pilih target: plan akan menentukan seberapa tinggi beban dinaikkan dan menambah latihan pace target."),
    "estimate now": ("Today you would run about <b>{est}</b> for {dist}.",
                     "Saat ini kamu kira-kira bisa <b>{est}</b> untuk {dist}."),
    "gap": ("Your target is <b>{gap}</b> faster.", "Target-mu <b>{gap}</b> lebih cepat dari itu."),
    "gap none": ("You are already at or under your target.", "Kamu sudah di bawah atau sama dengan target."),
    "weeks needed": ("At your recent rate of progress that takes about {weeks} weeks.",
                     "Dengan laju progresmu belakangan ini, butuh sekitar {weeks} minggu."),
    "trend flat": ("Your fitness has not shown a clear upward trend yet, so we cannot say how long it takes - "
                   "a few weeks of regular training will show it.",
                   "Kebugaranmu belum menunjukkan tren naik yang jelas, jadi belum bisa diperkirakan berapa lama - "
                   "beberapa minggu latihan rutin akan memperlihatkannya."),
    "by date": ("Race on {date} ({weeks} weeks): expected about {est}. Hitting the target needs {pct}% "
                "improvement a week - {verdict}.",
                "Race tanggal {date} ({weeks} minggu lagi): perkiraan sekitar {est}. Untuk kena target butuh "
                "kemajuan {pct}% per minggu - {verdict}."),
    "realistic": ("realistic", "realistis"),
    "ambitious": ("very ambitious; consider a later race or a softer target",
                  "sangat ambisius; pertimbangkan race yang lebih jauh atau target yang lebih longgar"),
    "build to": ("For this target the plan builds up to about <b>{peak} km a week</b>.",
                 "Untuk target ini plan naik bertahap sampai sekitar <b>{peak} km per minggu</b>."),
    "goal too fast": ("Goal pace {pace}/km is faster than you can hold in a tempo today ({tempo}/km), so there is "
                      "no goal-pace practice yet - it starts when your fitness catches up.",
                      "Pace target {pace}/km masih lebih cepat dari tempo yang bisa kamu tahan sekarang ({tempo}/km), "
                      "jadi belum ada latihan pace target - akan mulai saat kebugaranmu menyusul."),
    "goal beats": ("You are already faster than this target - consider a faster one.",
                   "Kamu sudah lebih cepat dari target ini - pertimbangkan target yang lebih cepat."),
    "goal within easy": ("Goal pace {pace}/km already feels easy on short runs; the challenge is holding it for "
                         "{dist} km, so the long runs (up to {long} km) matter most.",
                         "Pace target {pace}/km sudah terasa santai di lari pendek; tantangannya menahan pace itu "
                         "sejauh {dist} km, jadi long run (sampai {long} km) yang paling penting."),
    "goal finish": ("Long runs in build weeks end with {km} km at goal pace ({pace}/km).",
                    "Long run di minggu membangun ditutup {km} km di pace target ({pace}/km)."),
    "goal finish alt": ("Every other build week the long run ends at goal pace ({pace}/km): {km} km now, 0.5 km more "
                        "each time, up to {max} km. That is hard enough to be the week's hard session, so it replaces "
                        "the tempo run; the other weeks have intervals.",
                        "Setiap dua minggu sekali, long run di minggu membangun ditutup di pace target ({pace}/km): "
                        "sekarang {km} km, bertambah 0,5 km setiap kali, sampai {max} km. Itu cukup berat untuk jadi "
                        "sesi keras minggu itu, jadi menggantikan tempo run; minggu lainnya ada interval."),
    "sessions grow": ("Hard sessions grow each time they come round: intervals from 3 to 6 × 800 m, tempo from 2.5 "
                      "to 6 km. The extra distance comes out of the easy runs.",
                      "Sesi keras bertambah setiap kali datang: interval dari 3 ke 6 × 800 m, tempo dari 2,5 ke 6 km. "
                      "Tambahan jaraknya diambil dari easy run."),
    "why build goal": ("Your easy running is under control, so one harder session a week is added - a long run "
                       "with a goal-pace finish and intervals take turns.",
                       "Lari santaimu sudah terkendali, jadi ada satu sesi lebih keras per minggu - long run dengan "
                       "penutup pace target dan interval bergantian."),
    "no target peak": ("Without a target the plan builds to about <b>{peak} km a week</b> - the load that matches your "
                       "current level - and holds there. Pick a target to train for more.",
                       "Tanpa target, plan naik sampai sekitar <b>{peak} km per minggu</b> - beban yang sesuai "
                       "kemampuanmu sekarang - lalu bertahan di situ. Pilih target kalau mau berlatih lebih."),
    "session paces interval": ("800 m repeats at {interval}/km, set from your target.",
                               "Repetisi 800 m di {interval}/km, diatur dari target-mu."),
    "session paces": ("Tempo runs at {tempo}/km and 800 m repeats at {interval}/km, set from your target.",
                      "Tempo di {tempo}/km dan repetisi 800 m di {interval}/km, diatur dari target-mu."),
    "progress": ("This week {now} km · goal {peak} km a week", "Minggu ini {now} km · tujuan {peak} km per minggu"),
    "load chart": ("Weekly distance", "Jarak per minggu"),
    "actual": ("Run", "Dilari"),
    "planned": ("Planned", "Rencana"),
    "peak line": ("Target build-up", "Puncak target"),
    "km per week": ("km per week", "km per minggu"),

    # ---- programs ----
    "nav today": ("Today", "Hari ini"),
    "nav programs": ("Programs", "Program"),
    "programs title": ("Your training programs", "Program latihanmu"),
    "no programs": ("No program yet. Make one below: pick what you train for, and the plan and calendar follow.",
                    "Belum ada program. Buat di bawah: pilih untuk apa kamu latihan, plan dan kalendernya menyusul."),
    "active": ("active", "aktif"),
    "program upcoming": ("not started", "belum mulai"),
    "program running": ("running", "berjalan"),
    "program finished": ("finished", "selesai"),
    "week of": ("week {n} of {total}", "minggu {n} dari {total}"),
    "race on": ("race {date}", "race {date}"),
    "n weeks": ("{n} weeks", "{n} minggu"),
    "from date": ("from {date}", "mulai {date}"),
    "open program": ("Open program", "Buka program"),
    "all programs": ("All programs", "Semua program"),
    "new program": ("New program", "Buat program baru"),
    "program name": ("Name", "Nama"),
    "start date": ("Start", "Mulai"),
    "length weeks": ("Length (weeks)", "Lama (minggu)"),
    "estimate today": ("Your estimate today: {est}", "Perkiraanmu saat ini: {est}"),
    "make active": ("Make it the active program", "Jadikan program aktif"),
    "save program": ("Save program", "Simpan program"),
    "make active now": ("Make active", "Jadikan aktif"),
    "active program": ("Active program", "Program aktif"),
    "no active program": ("No active program: this is a plan without a target, from today.",
                          "Belum ada program aktif: ini plan tanpa target, mulai hari ini."),
    "make program": ("Make a program", "Buat program"),
    "calendar": ("Calendar", "Kalender"),
    "calendar hint": ("Hover over a day (or tap it on a phone) for its menu.",
                      "Arahkan kursor ke satu hari (atau ketuk di HP) untuk melihat menunya."),
    "full menu": ("Full menu", "Menu lengkap"),
    "day menu": ("Day menu", "Menu hari itu"),
    "pick a day": ("Tap a day in the calendar to see its menu.", "Ketuk satu hari di kalender untuk melihat menunya."),
    "you ran": ("You ran {km} km at {pace}/km, average heart rate {hr}.",
                "Kamu lari {km} km di {pace}/km, detak jantung rata-rata {hr}."),
    "all weeks": ("Every week", "Semua minggu"),
    "edit program": ("Edit program", "Ubah program"),
    "edit note": ("Finished weeks stay as they were; the weeks ahead are planned again from your change.",
                  "Minggu yang sudah selesai tetap seperti semula; minggu ke depan disusun ulang dari perubahanmu."),
    "save changes": ("Save changes", "Simpan perubahan"),
    "delete program": ("Delete program", "Hapus program"),
    "delete sure": ("Yes, delete this program and its saved weeks", "Ya, hapus program ini beserta minggu-minggu tersimpannya"),
    "delete now": ("Delete", "Hapus"),

    # ---- coming weeks ----
    "coming weeks": ("Coming weeks", "Minggu-minggu berikutnya"),
    "coming note": ("Future weeks are estimates; they update as new runs come in. Every week is evaluated "
                    "when it ends.",
                    "Minggu ke depan masih perkiraan dan berubah mengikuti lari barumu. Setiap minggu "
                    "dievaluasi begitu selesai."),
    "col week": ("week", "minggu"),
    "col dates": ("dates", "tanggal"),
    "col type": ("type", "jenis"),
    "col long": ("long run km", "long run km"),
    "col runs": ("runs", "lari"),
    "col status": ("status", "status"),
    "col result": ("result", "hasil"),
    "status done": ("evaluated", "dievaluasi"),
    "status current": ("this week", "minggu ini"),
    "status needs data": ("waiting for sync", "menunggu sinkron"),
    "status upcoming": ("planned", "rencana"),
    "eval": ("{actual} of {planned} km · {runs} of {planned_runs} runs · {long}{easy}",
             "{actual} dari {planned} km · {runs} dari {planned_runs} lari · {long}{easy}"),
    "eval long done": ("long run done", "long run selesai"),
    "eval long missed": ("long run missed - it will not grow next week", "long run terlewat - minggu depan tidak naik"),
    "eval easy": (" · {pct}% easy", " · {pct}% santai"),
    "no runs weeks": ("No runs recorded in the week(s) of {weeks} - counted as 0 km. If you did run, sync again.",
                      "Tidak ada lari tercatat di minggu {weeks} - dihitung 0 km. Kalau kamu lari, sinkronkan lagi."),

    # ---- safety ----
    "safety ok": ("Safety checks: all {n} OK for this week.", "Cek keamanan: semua {n} aman untuk minggu ini."),
    "safety watch": ("Safety checks: {k} thing(s) to watch this week", "Cek keamanan: {k} hal perlu diperhatikan minggu ini"),
    "safety details": ("All checks with formulas and sources", "Semua cek beserta rumus dan sumbernya"),
    "check weekly 10%": ("This week ({planned} km) is a little above the cautious +10% guideline ({limit} km). "
                         "Research finds up to +30% no riskier, so this is just a note.",
                         "Minggu ini ({planned} km) sedikit di atas patokan hati-hati +10% ({limit} km). Riset "
                         "menunjukkan sampai +30% tidak lebih berisiko, jadi ini sekadar catatan."),
    "check two-week 30%": ("This week is {change}% more than the last 7 days - above the 30% limit. "
                           "Shorten a run or two.",
                           "Minggu ini {change}% lebih banyak dari 7 hari terakhir - lewat batas 30%. "
                           "Pendekkan satu atau dua lari."),
    "check two-week none": ("No runs in the last 7 days: restart with short, easy runs.",
                            "Tidak ada lari 7 hari terakhir: mulai lagi dengan lari pendek dan santai."),
    "check rising weeks": ("Distance has gone up three weeks in a row - a lighter week soon is wise.",
                           "Jarak naik tiga minggu berturut-turut - sebaiknya segera ada minggu ringan."),
    "check long run step": ("The long run ({long} km) is more than 1.5 km longer than your recent longest "
                            "({longest} km).",
                            "Long run ({long} km) lebih dari 1,5 km di atas lari terjauhmu belakangan ini ({longest} km)."),
    "check hard after race": ("A hard session is planned within two weeks of your race - keep it easy instead.",
                              "Ada sesi keras dalam dua minggu setelah race - sebaiknya diganti lari santai."),
    "check post-race rest": ("A run is planned in the first 3 days after your race - rest instead.",
                             "Ada lari di 3 hari pertama setelah race - sebaiknya istirahat."),
    "check load spike": ("This week is {ratio}× your usual load of the last 3 weeks ({usual} km a week).",
                         "Minggu ini {ratio}× beban biasamu dalam 3 minggu terakhir ({usual} km per minggu)."),
    "level pass": ("ok", "aman"), "level info": ("note", "catatan"),
    "level caution": ("watch", "perhatikan"), "level high": ("high", "tinggi"),

    # ---- at a glance ----
    "at a glance": ("Your running so far", "Larimu sejauh ini"),
    "last race": ("Last race", "Race terakhir"),
    "faster than": ("{diff} faster than {race}", "{diff} lebih cepat dari {race}"),
    "slower than": ("{diff} slower than {race}", "{diff} lebih lambat dari {race}"),
    "race pace": ("pace {pace}/km", "pace {pace}/km"),
    "no race yet": ("No race yet", "Belum ada race"),
    "mark race hint": ("Set Event Type to Race in Garmin Connect", "Set Event Type ke Race di Garmin Connect"),
    "fitness": ("Aerobic fitness", "Kebugaran aerobik"),
    "fitness value": ("{pace}/km at heart rate {hr}", "{pace}/km di detak jantung {hr}"),
    "fitness change": ("{s} s/km faster than {month} - faster at the same heart rate means fitter",
                       "{s} dtk/km lebih cepat dari {month} - lebih cepat di detak jantung yang sama artinya lebih bugar"),
    "fitness change slower": ("{s} s/km slower than {month}", "{s} dtk/km lebih lambat dari {month}"),
    "easy share": ("Easy running", "Lari santai"),
    "easy value": ("{pct}% of your time", "{pct}% dari waktumu"),
    "easy low": ("Aim for about 80%: most of your runs were harder than easy (heart rate above {hr}).",
                 "Idealnya sekitar 80%: sebagian besar larimu lebih keras dari santai (detak jantung di atas {hr})."),
    "easy ok": ("On target: most of your running is easy.", "Sesuai target: sebagian besar larimu santai."),
    "go deeper": ("Go deeper", "Lebih dalam"),
    "how calc": ("How is this calculated?", "Bagaimana ini dihitung?"),

    # ---- deep-dive tabs ----
    "tab races": ("Races", "Race"),
    "tab fitness": ("Fitness", "Kebugaran"),
    "tab easy": ("Easy vs hard", "Santai vs keras"),
    "tab heat": ("Heat", "Panas"),
    "pm title": ("What changed between your last two races?", "Apa yang berubah di antara dua race terakhirmu?"),
    "pm needs two": ("This needs two races. Set Event Type to Race on your race activities in Garmin Connect.",
                     "Butuh dua race. Set Event Type ke Race di aktivitas race-mu di Garmin Connect."),
    "pm training": ("Training in the {weeks} weeks before each race", "Latihan {weeks} minggu sebelum tiap race"),
    "pm how": ("Races are activities with Event Type Race in Garmin Connect (or listed in config.py); the last "
               "two are compared. For each, the {weeks} weeks before the start are summarised; the race itself "
               "is left out.",
               "Race = aktivitas dengan Event Type Race di Garmin Connect (atau tercantum di config.py); dua yang "
               "terakhir dibandingkan. Untuk tiap race, {weeks} minggu sebelum start diringkas; race-nya sendiri "
               "tidak dihitung."),
    "fit title": ("Are you getting faster at the same heart rate?", "Apakah kamu makin cepat di detak jantung yang sama?"),
    "fit each": ("Each run", "Tiap lari"),
    "fit month": ("Monthly typical (3+ runs)", "Rata-rata bulanan (3+ lari)"),
    "fit axis": ("pace at heart rate {hr} (faster ↑)", "pace di detak jantung {hr} (lebih cepat ↑)"),
    "fit summary": ("Typical month: <b>{first} → {last} /km</b> at heart rate {hr}. Months with fewer than 3 runs "
                    "are dots only.",
                    "Bulan biasa: <b>{first} → {last} /km</b> di detak jantung {hr}. Bulan dengan kurang dari 3 lari "
                    "hanya tampil sebagai titik."),
    "fit how": ("Each run is converted to the pace you would run at heart rate {hr}: efficiency = speed ÷ heart "
                "rate, then pace = 1000 ÷ (efficiency × {hr}). Races are left out. Most reliable near your usual "
                "heart rate.",
                "Tiap lari diubah menjadi pace yang kira-kira kamu lari di detak jantung {hr}: efisiensi = kecepatan "
                "÷ detak jantung, lalu pace = 1000 ÷ (efisiensi × {hr}). Race tidak dihitung. Paling akurat di "
                "sekitar detak jantung biasamu."),
    "easy title": ("Were your easy runs actually easy?", "Apakah lari santaimu benar-benar santai?"),
    "easy bar": ("Easy (heart rate ≤ {hr})", "Santai (detak jantung ≤ {hr})"),
    "hard bar": ("Harder (heart rate > {hr})", "Lebih keras (detak jantung > {hr})"),
    "minutes week": ("minutes per week", "menit per minggu"),
    "race mark": ("race", "race"),
    "easy summary": ("Overall <b>{pct}% easy</b> (aim for about {target}%). Weeks on target: <b>{on} of {n}</b>.",
                     "Total <b>{pct}% santai</b> (idealnya sekitar {target}%). Minggu yang sesuai target: <b>{on} dari {n}</b>."),
    "wrong easy": ("Runs you called easy that were not ({n})", "Lari yang kamu sebut santai tapi ternyata tidak ({n})"),
    "col date": ("date", "tanggal"), "col title": ("title", "judul"), "col avg hr": ("avg heart rate", "detak jantung rata-rata"),
    "col above": ("above easy by", "di atas batas santai"),
    "easy how": ("Easy = heart rate at or below {hr} (80% of your max {max}). Runs with an activity file count "
                 "the actual seconds below {hr}; older runs use their average heart rate.",
                 "Santai = detak jantung sampai {hr} (80% dari maksimalmu {max}). Lari yang punya file aktivitas "
                 "dihitung per detik di bawah {hr}; lari lama memakai detak jantung rata-ratanya."),
    "heat title": ("How much did heat and humidity slow each run?", "Seberapa besar panas dan lembap memperlambat tiap lari?"),
    "heat series": ("Heat slowdown", "Perlambatan karena panas"),
    "heat axis": ("expected slowdown", "perkiraan perlambatan"),
    "heat summary": ("Heat costs you about <b>{median}%</b> on a typical run (range {low}-{high}%).",
                     "Panas membuatmu sekitar <b>{median}%</b> lebih lambat di lari biasa (rentang {low}-{high}%)."),
    "heat similar": (" Your last two races had similar heat ({a}% and {b}%), so the difference between them is not the weather.",
                     " Dua race terakhirmu sama panasnya ({a}% dan {b}%), jadi bedanya bukan karena cuaca."),
    "heat differed": (" Heat differed between your last two races ({a}% vs {b}%): compare their heat-adjusted paces.",
                      " Panas di dua race terakhirmu berbeda ({a}% vs {b}%): bandingkan pace setelah dikoreksi panas."),
    "heat how": ("Air temperature and dew point come from Open-Meteo for each run's hour (your watch reads too "
                 "warm on your wrist). Slowdown follows a common rule of thumb: temperature °F + dew point °F. "
                 "A guide for comparing runs, not an exact law - slower runners likely lose more.",
                 "Suhu udara dan titik embun diambil dari Open-Meteo untuk jam tiap lari (sensor jam terlalu panas "
                 "karena menempel di kulit). Perlambatan memakai aturan praktis: suhu °F + titik embun °F. Panduan "
                 "untuk membandingkan lari, bukan hukum pasti - pelari yang lebih lambat kemungkinan kehilangan lebih banyak."),
    "table": ("Table", "Tabel"),
    "hr settings": ("Heart-rate settings - why these numbers?", "Pengaturan detak jantung - kenapa angka ini?"),

    # ---- sidebar weather ----
    "weather title": ("{city} weather", "Cuaca {city}"),
    "refresh": ("Refresh forecast", "Perbarui prakiraan"),
    "now": ("Now", "Sekarang"),
    "next hours": ("Next hours", "Beberapa jam ke depan"),
    "col sky": ("sky", "langit"), "col rain": ("rain", "hujan"),
    "run time today": ("Your run time today ({start}-{end})", "Jam larimu hari ini ({start}-{end})"),
    "run time tomorrow": ("Your run time tomorrow ({start}-{end})", "Jam larimu besok ({start}-{end})"),
    "forecast updated": ("Updated {time} · Open-Meteo · info only, the plan does not change. Air quality is a model estimate.",
                         "Diperbarui {time} · Open-Meteo · info saja, plan tidak berubah. Kualitas udara adalah perkiraan model."),
    "forecast none": ("Forecast unavailable - no internet and no saved forecast.",
                      "Prakiraan tidak tersedia - tidak ada internet dan belum ada data tersimpan."),
    "air now": ("Air right now: <b>AQI {aqi} - {label}</b> (measured by IQAir at {station}, {time})",
                "Udara sekarang: <b>AQI {aqi} - {label}</b> (diukur IQAir di {station}, {time})"),
    "sky clear": ("clear", "cerah"), "sky partly cloudy": ("partly cloudy", "berawan sebagian"),
    "sky cloudy": ("cloudy", "berawan"), "sky fog": ("fog", "kabut"), "sky drizzle": ("drizzle", "gerimis"),
    "sky rain": ("rain", "hujan"), "sky showers": ("showers", "hujan lokal"), "sky thunderstorm": ("thunderstorm", "badai petir"),
    "aqi good": ("good", "baik"), "aqi moderate": ("moderate", "sedang"),
    "aqi unhealthy for sensitive groups": ("unhealthy for sensitive groups", "tidak sehat bagi kelompok sensitif"),
    "aqi unhealthy": ("unhealthy", "tidak sehat"), "aqi very unhealthy": ("very unhealthy", "sangat tidak sehat"),
    "aqi hazardous": ("hazardous", "berbahaya"),
}

# Labels of the post-mortem table (src/analysis/race_postmortem.py METRICS), by key.
METRIC_LABELS = {
    "runs_per_week": ("Runs per week", "Lari per minggu"),
    "km_per_week": ("Distance per week (km)", "Jarak per minggu (km)"),
    "longest_run_km": ("Longest run (km)", "Lari terjauh (km)"),
    "weeks_with_runs": ("Weeks with at least 1 run", "Minggu dengan minimal 1 lari"),
    "avg_hr": ("Average heart rate", "Detak jantung rata-rata"),
    "easy_time_pct": ("Easy time (%)", "Waktu santai (%)"),
    "efficiency": ("Efficiency (higher = fitter)", "Efisiensi (makin tinggi makin bugar)"),
    "heat_slowdown_pct": ("Heat slowdown (%)", "Perlambatan karena panas (%)"),
}


class Text:
    """t = Text("id"); t("keep hr", lo=137, hi=157); t.day(date); t.date(date)"""

    def __init__(self, lang):
        self.lang = lang if lang in LANGUAGES else "id"
        self.i = 0 if self.lang == "en" else 1

    def __call__(self, key, **values):
        text = TEXT[key][self.i]
        return text.format(**values) if values else text

    def get(self, key, default=""):
        """Like calling, but for keys that may not exist (e.g. a new sky type)."""
        return TEXT[key][self.i] if key in TEXT else default

    def metric(self, key):
        return METRIC_LABELS[key][self.i]

    def day(self, d, long=False):
        return (DAYS_LONG if long else DAYS)[self.lang][d.weekday()]

    def date(self, d, weekday=True, long=False):
        """'Thu 29 Oct' / 'Kam 29 Okt' (long=True: 'Kamis 29 Okt')."""
        text = f"{d.day} {MONTHS[self.lang][d.month - 1]}"
        return f"{self.day(d, long)} {text}" if weekday else text

    def month(self, period):
        return f"{MONTHS[self.lang][period.month - 1]} {period.year}"
