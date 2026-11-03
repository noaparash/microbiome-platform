# מדריך התקנה בשרת — Microbiome Platform

מדריך צעד-אחר-צעד (runbook) להתקנת הפלטפורמה בשרת של המעבדה. כל פקודה מופיעה כמו שהיא — מעתיקים ומדביקים. ההנחה: שרת **Linux מסוג Ubuntu 22.04 או 24.04** עם הרשאות `sudo`. אם השרת אחר — לשאול את ה-IT; רוב הצעדים זהים, רק פקודות ההתקנה שונות.

> **עיקרון:** הנתונים שמועלים יכולים להיות קליניים. לכן ברירת המחדל היא **סגורה**: האתר נגיש רק מרשת המעבדה / VPN, ב-HTTPS בלבד, והקבצים נגישים רק לחשבון השירות.

---

## ✅ רשימת החלטות — מה צריך מהמעבדה לפני ההתקנה

| # | החלטה | ממי | למה זה חשוב | הערך שנבחר |
|---|---|---|---|---|
| 1 | **איזה שרת** — שם/כתובת, מערכת הפעלה (Ubuntu?), מעבדים, זיכרון, דיסק | IT / הפרופסור | צריך Linux, ‏≥4 ליבות, **‏≥16GB זיכרון** (ראו "דאטהסטים גדולים" למטה), ‏≥20GB דיסק לתוכנה + מקום לנתונים | |
| 2 | **כתובת האתר (hostname)** — למשל `microbiome.<lab>.biu.ac.il` | IT | הכתובת שמשתמשים פותחים; נכנסת להגדרות ולתעודה | |
| 3 | **תעודת HTTPS** — מ-IT של האוניברסיטה, או Let's Encrypt (רק אם השרת נגיש מהאינטרנט) | IT | בלי HTTPS הנתונים עוברים ברשת לא מוצפנים | |
| 4 | **מי רשאי לגשת** — רשת המעבדה? VPN של האוניברסיטה? חשבונות משתמש (לא קיימים עדיין)? | הפרופסור + IT | ברירת המחדל: **רק רשת המעבדה + VPN**. פתיחה לאינטרנט — רק בהחלטה מפורשת. צריך את טווחי הכתובות (CIDR) מה-IT | |
| 5 | **שרת מייל (SMTP)** — כתובת שרת, פורט, משתמש וסיסמה, כתובת שולח | IT / המעבדה | בלי זה המייל פשוט כבוי — הכול עובד, משתמשים שומרים את הקישור | |
| 6 | **מדיניות דיסק ושמירת נתונים** — כמה זמן לשמור ניתוחים (למשל 90 יום)? מי מריץ את הניקוי ומתי? | הפרופסור | ניתוחים ישנים תופסים מקום ומכילים נתונים רגישים. הניקוי **ידני** ומתועד | |
| 7 | **גיבוי** — לגבות את תיקיית הנתונים או לא? (היא רגישה; גיבוי = עוד עותק לשמור עליו) | הפרופסור + IT | החלטה מודעת בכל מקרה | |
| 8 | **מי מנהל את השרת** — מי מקבל `sudo`, מי מעדכן גרסאות | הפרופסור | מישהו צריך להיות אחראי | |
| 9 | **הרשאה לשכפל את הקוד** — הריפו ב-GitHub פרטי; השרת צריך גישה (deploy key) | בעלת הריפו | בלי זה אי אפשר להוריד את הקוד לשרת | |

---

## מה רץ בשרת (תמונה כללית)

```
משתמש (רשת המעבדה / VPN)
   │  HTTPS
   ▼
nginx            ← HTTPS, הגבלת גישה לפי רשת, גודל העלאה
   │  רק בתוך השרת (127.0.0.1:8000)
   ▼
microplatform-web     (gunicorn)  ← מציג דפים ומכניס ניתוחים לתור. לא מריץ ניתוחים.
   │  תור על הדיסק: /var/lib/microplatform/runs
   ▼
microplatform-worker  ← מריץ את הניתוחים, **אחד בכל פעם**, לפי סדר
```

- **iMic רץ על המעבד (CPU)**, לא על כרטיס גרפי — כ-8 שניות לאימון על 257 דגימות. (הקוד שפורסם קורס על GPU; הפלטפורמה עוקפת זאת ומשתמשת ב-CPU.)
- **ה"עובד" מריץ ניתוח אחד בכל פעם.** אם שני אנשים לוחצים Run יחד, השני רואה "Waiting to start…" עד שהראשון מסתיים. בדאטהסטים קטנים (מאות טקסונים) כל ניתוח לוקח עד כ-2 דקות; GIMIC גדל בריבוע מספר הדגימות.
- **דאטהסטים גדולים — צריך את שרת המעבדה, לא מחשב נייד.** חלק מהכלים איטיים וצורכים הרבה זיכרון כשהטבלה גדולה מאוד. במדידה על FRANZOSA (220 דגימות, כ-56 אלף טקסונים) במחשב נייד: העיבוד המקדים (MIPMLP) לקח כ-15 דקות, ו-**miMic לא הסתיים תוך 60 דקות, עם שיא זיכרון של 8.79GB**. לכן הדרישה היא **לפחות 16GB זיכרון** — כדי שניתוח כזה יסתיים בלי להיתקע, והשרת ימשיך לעבוד בזמן הזה. טבלת זמני הריצה המלאה תצורף כשהמדידה תסתיים.
- **הפעלה מחדש לא מאבדת ניתוח:** כשעוצרים או מפעילים מחדש את ה"עובד", הוא **מסיים את הניתוח שרץ** ורק אז נעצר (עד **4 שעות**, `TimeoutStopSec=4h` — כדי שגם ניתוח ארוך, כמו miMic על דאטהסט גדול, יסתיים ולא ייקטע. נכוונן את הערך לפי טבלת זמני הריצה). כשאין ניתוח שרץ, העצירה מיידית. **שימו לב:** בזמן ניתוח ארוך, גם `systemctl restart` וגם אתחול של השרת יחכו עד שהניתוח יסתיים. כדי לעצור מיד בכל זאת: `sudo systemctl kill microplatform-worker` (הניתוח יסומן "interrupted, please run again"). אם השרת נופל באמצע — הניתוח מסומן "interrupted, please run again".
- **אין הגבלת זמן על ניתוח בפעולה רגילה:** כל עוד לא עוצרים את ה"עובד", ניתוח רץ עד שהוא מסתיים, כמה זמן שייקח. ה"עובד" מסמן כל 10 שניות שהוא חי. ניתוח מסומן כ-interrupted **רק כשהתהליך שמריץ אותו באמת כבר לא קיים**: גם אם הסימון מתעכב (למשל בחישוב ארוך), לפני הסימון נבדק במערכת ההפעלה שהתהליך הזה, עם אותו זמן התחלה, כבר לא רץ. זה נכון בכל הגדרה, גם עם כמה "עובדים". חריג אחד: "עובד" במחשב אחר שחולק את אותה תיקייה — אותו אי אפשר לבדוק, ושם קובע הסימון. דף התוצאות ממשיך להתעדכן כל הזמן, וכלי הניקוי הידני לא נוגע בניתוחים שממתינים או רצים.

---

## שלב 1 — התקנת תוכנות הבסיס

```bash
sudo apt update
sudo apt install -y git nginx software-properties-common
# Python 3.13 (אם אינו מותקן כבר; ב-Ubuntu דרך deadsnakes):
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt install -y python3.13 python3.13-venv
python3.13 --version        # צריך להדפיס Python 3.13.x
```

## שלב 2 — חשבון שירות ותיקיות

חשבון מיוחד בלי סיסמה ובלי כניסה, שרק הוא קורא את הנתונים:

```bash
sudo adduser --system --group --home /var/lib/microplatform microplatform
sudo mkdir -p /var/lib/microplatform /etc/microplatform
sudo chown microplatform:microplatform /var/lib/microplatform
sudo chmod 700 /var/lib/microplatform          # רק חשבון השירות קורא את הנתונים
```

## שלב 3 — הורדת הקוד

```bash
sudo git clone <כתובת הריפו> /opt/microplatform
cd /opt/microplatform
sudo git checkout <גרסה, למשל main>
```

הקוד שייך ל-root וחשבון השירות רק קורא אותו — כך אף אחד לא משנה קוד דרך האתר.

## שלב 4 — סביבה וירטואלית והתקנה

```bash
sudo python3.13 -m venv /opt/microplatform/.venv
sudo /opt/microplatform/.venv/bin/python -m pip install --upgrade pip
sudo /opt/microplatform/.venv/bin/python -m pip install "/opt/microplatform[server]"
```

- זו הורדה גדולה (PyTorch ועוד, כ-1–2GB) ולוקחת כמה דקות.
- `[server]` מוסיף את gunicorn (שרת האתר לייצור).

בדיקה שההתקנה תקינה:

```bash
/opt/microplatform/.venv/bin/python -c "import microplatform, MIPMLP, mimic_da, samba; print('ok', microplatform.__version__)"
```

## שלב 5 — קובץ ההגדרות (מחוץ ל-Git)

```bash
sudo install -m 640 -o root -g microplatform /opt/microplatform/deploy/microplatform.env.example /etc/microplatform/microplatform.env
python3 -c "import secrets; print(secrets.token_hex(32))"     # מעתיקים את הפלט
sudo nano /etc/microplatform/microplatform.env
```

בקובץ ממלאים:
- `MICROPLATFORM_SECRET_KEY=` ← הערך שהודפס. **לעולם לא לשים אותו ב-Git או לשלוח במייל.**
- `MICROPLATFORM_PUBLIC_URL=` ← `https://<כתובת האתר>`
- את הגדרות ה-SMTP **משאירים ריקות** עד שהמעבדה תספק אותן (המייל כבוי עד אז).
- `MICROPLATFORM_JOBS=external` כבר מוגדר — האתר רק מכניס לתור, ה"עובד" מריץ.

בדיקה שהאתר נטען עם ההגדרות (בלי להפעיל אותו):

```bash
sudo -u microplatform bash -c 'set -a; . /etc/microplatform/microplatform.env; set +a; /opt/microplatform/.venv/bin/python -c "import microplatform.web.wsgi as w; print(\"ok:\", w.app.config[\"JOBS\"])"'
# צריך להדפיס: ok: external
```

## שלב 6 — שירותי המערכת (מתחילים לבד באתחול, מתאוששים מנפילה)

```bash
sudo cp /opt/microplatform/deploy/systemd/microplatform-web.service /etc/systemd/system/
sudo cp /opt/microplatform/deploy/systemd/microplatform-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now microplatform-web microplatform-worker
sudo systemctl status microplatform-web microplatform-worker      # שניהם צריכים להיות "active (running)"
```

## שלב 7 — HTTPS והגבלת גישה (nginx)

1. מקבלים מה-IT את קובצי התעודה ושמים אותם ב:
   `/etc/ssl/certs/<HOSTNAME>.crt` ו-`/etc/ssl/private/<HOSTNAME>.key` (המפתח: `chmod 600`).
2. מתקינים את ההגדרה וממלאים את כל ה-`<...>` — שם האתר וטווחי הרשת (CIDR) שה-IT נתן:

```bash
sudo cp /opt/microplatform/deploy/nginx/microplatform.conf /etc/nginx/sites-available/microplatform
sudo nano /etc/nginx/sites-available/microplatform
sudo ln -s /etc/nginx/sites-available/microplatform /etc/nginx/sites-enabled/
sudo nginx -t                 # צריך: "syntax is ok" ו-"test is successful"
sudo systemctl reload nginx
```

**ברירת המחדל סגורה:** רק הטווחים שב-`allow` נכנסים; כל השאר מקבלים 403. פתיחה לאינטרנט (מחיקת שורות `allow/deny`) — רק אחרי החלטה מפורשת (שורה 4 ברשימה), ועדיף יחד עם חשבונות משתמש, שעוד לא קיימים.

## שלב 8 — בדיקה שהכול עובד

1. ממחשב **ברשת המעבדה**: לפתוח `https://<כתובת האתר>` — דף הבית עם שורת המעבדה.
2. ללחוץ **Example** ← **Analyse the example** ← **Run**. הדף מציג "Running…" ואז את התוצאות.
3. ממחשב **מחוץ** לרשת (למשל טלפון בלי VPN): צריך לקבל **403 Forbidden**.
4. ביומנים (logs):

```bash
journalctl -u microplatform-worker -n 30     # צריך: "watching /var/lib/microplatform/runs (one run at a time)"
journalctl -u microplatform-web -n 30
```

---

## תפעול יומיומי

| מה | פקודה |
|---|---|
| מצב השירותים | `sudo systemctl status microplatform-web microplatform-worker` |
| עצירה | `sudo systemctl stop microplatform-web microplatform-worker` |
| הפעלה | `sudo systemctl start microplatform-web microplatform-worker` |
| הפעלה מחדש (אחרי שינוי הגדרות) | `sudo systemctl restart microplatform-web microplatform-worker` |
| יומן חי של ה"עובד" | `journalctl -u microplatform-worker -f` |

- **עצירה/הפעלה מחדש של ה"עובד" מחכה שהניתוח הנוכחי יסתיים** (עד 4 שעות) — זה תקין, לא תקוע. לעצירה מיידית: `sudo systemctl kill microplatform-worker`.
- היומנים **לא** מכילים את כתובות הניתוחים: כתובת ניתוח היא כמו מפתח, ומי שיש לו אותה רואה את התוצאות.

### עדכון לגרסה חדשה

```bash
cd /opt/microplatform && sudo git pull
sudo /opt/microplatform/.venv/bin/python -m pip install "/opt/microplatform[server]"
sudo systemctl restart microplatform-web microplatform-worker
```

### שמירת נתונים וניקוי (ידני בלבד — לעולם לא אוטומטי)

לפי המדיניות שנקבעה (שורה 6), למשל פעם בחודש:

```bash
# 1. רשימה בלבד — לא מוחקת כלום:
sudo -u microplatform /opt/microplatform/.venv/bin/python -m microplatform.retention --instance /var/lib/microplatform --older-than 90
# 2. מחיקה — שואלת לאישור (מקלידים delete):
sudo -u microplatform /opt/microplatform/.venv/bin/python -m microplatform.retention --instance /var/lib/microplatform --older-than 90 --delete
```

- ניתוחים שבתור או רצים **לעולם לא נמחקים**.
- כל מחיקה נרשמת ב-`/var/lib/microplatform/retention.log` (מזהה ניתוח, תאריך יצירה, גודל, מי מחק, מתי) — **בלי** שמות קבצים או נתונים.
- `--include-cache` מוחק גם את המטמון של העיבוד המקדים (נבנה מחדש לבד כשצריך).

---

## פתרון בעיות

| מה רואים | מה זה כנראה | מה עושים |
|---|---|---|
| **502 Bad Gateway** | שירות האתר לא רץ | `sudo systemctl status microplatform-web`, ואז `journalctl -u microplatform-web -n 50` |
| השירות לא עולה, ביומן: `MICROPLATFORM_SECRET_KEY is not set` | חסר מפתח בקובץ ההגדרות | שלב 5 |
| ניתוח נשאר **"Waiting to start…"** | ה"עובד" לא רץ | `sudo systemctl status microplatform-worker` |
| **403 Forbidden** | המחשב לא ברשת המורשית | להתחבר ל-VPN, או להוסיף את הטווח ב-nginx (בהחלטה) |
| "That upload is larger than … MB" | הקובץ גדול מהמגבלה | להגדיל `MICROPLATFORM_MAX_UPLOAD_MB` **וגם** `client_max_body_size` ב-nginx, ואז restart/reload |
| ניתוח מסומן "interrupted" | השרת/ה"עובד" נפל באמצע | ללחוץ Run שוב |

---

## הערות אבטחה

- **HTTPS בלבד**; הגישה מוגבלת לרשת המעבדה / VPN; אין חשבונות משתמש עדיין — כל מי שברשת המורשית יכול להעלות, ומי שיש לו קישור לניתוח יכול לראות אותו. לכן: לשתף קישורים רק בתוך הצוות.
- תיקיות הניתוחים נגישות רק לחשבון השירות (הרשאות 700, ‏`UMask=0077`); השירותים יכולים לכתוב רק ל-`/var/lib/microplatform`.
- הסודות (מפתח האתר, סיסמת SMTP) רק ב-`/etc/microplatform/microplatform.env` (הרשאות 640), לא ב-Git.
- דפי תוצאות לא נשמרים במטמון של הדפדפן (`Cache-Control: no-store`).
