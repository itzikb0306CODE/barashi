# אוטומציית ניהול נכסים — בדיקת בנק ← אישור תשלום ב-OXS ← וואטסאפ

סקריפט שקורא קובץ אקסל של תנועות בנק (מכל בניין), מזהה שורות שהן תשלומי
דיירים, מתאים אותן לפי שם לדייר במערכת OXS, מאשר את התשלום ב-OXS (מה
שגורם ל-OXS לשלוח מייל אישור אוטומטית), ואז שולח גם הודעת וואטסאפ לדייר.
שורות הוצאה (חיוב) נרשמות כהוצאת בניין ב-OXS.

## מגבלה חשובה: ה-API של OXS

לפי מדריך מפתחות ה-API, המודולים "חובות דיירים" ו"מידע כללי" (שכולל
היסטוריית תשלומים) הם **קריאה בלבד**. אין endpoint לאישור תשלום. לכן
האישור בפועל מתבצע ע"י אוטומציית דפדפן (Playwright) שמדמה בדיוק את מה
שאדם עושה ידנית במסכי OXS.

## ⚠️ הסלקטורים בקובץ oxs_client.py הם ניחוש מבוסס-צילומי-מסך

הקוד נכתב בסביבה ללא גישת רשת ל-oxs.co.il, לכן לא נבדק חי מול האתר.
השדות והכפתורים ("בצע תשלום", "המשך לתשלום", שמות השדות) מבוססים על
צילומי מסך אמיתיים ששלחת, אבל **חובה הרצה ראשונה מבוקרת** לפני שסומכים
על זה:

```bash
# בפעם הראשונה, הרץ עם דפדפן גלוי ואיטי כדי לצפות שהוא באמת לוחץ נכון:
OXS_HEADLESS=false OXS_SLOW_MO_MS=300 python -m automation.main buildings.json
```

אם שלב מסוים נכשל (לדוגמה `_fill_field_near_label` לא מוצא שדה), הפונקציה
הרלוונטית ב-`automation/oxs_client.py` היא מקום מבודד וברור לתקן —
אפשר גם להריץ `playwright codegen https://pro.oxs.co.il` כדי להקליט את
הלחיצות בפועל ולהעתיק את הסלקטור המדויק.

## התקנה

```bash
python -m venv .venv
source .venv/bin/activate   # ב-Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## הגדרה

1. `cp .env.example .env` ומלאו: משתמש/סיסמת OXS, ופרטי WhatsApp Business
   Cloud API (`WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`,
   `WHATSAPP_TEMPLATE_NAME`).

   **וואטסאפ:** ההודעה נשלחת ביוזמת העסק (לא בתגובה להודעה מהדייר), ולכן
   **חייבת** להשתמש בתבנית הודעה מאושרת מראש ב-Meta Business Manager
   (WhatsApp Manager → Message Templates) — הודעת טקסט חופשי תידחה ע"י ה-API.

2. `cp buildings.example.json buildings.json` ומלאו לכל בניין: שם (ללוגים
   בלבד), `oxs_building_id` (מה-URL של הבניין ב-OXS,
   `.../building/<זה>/payments-list`), ונתיב לקובץ האקסל של הבנק (שמים
   ב-`data/`, שלא נכנס ל-git).

## הרצה

```bash
python -m automation.main buildings.json
```

התוצאה: קובץ לוג `run_*.log` וקובץ ביקורת `audit_*.csv` עם כל שורה
שנבדקה — הותאמה או לא, ולמה. שני הקבצים לא נכנסים ל-git (הם מכילים שמות
וסכומים אמיתיים).

## בטיחות ההתאמה

התאמת שם דייר לתשלום היא **fuzzy match** (`automation/matcher.py`) עם סף
ביטחון ודרישת פער ברור מהמועמד השני. שורה שההתאמה שלה לא חד-משמעית
**מדולגת ונרשמת בלוג ובקובץ הביקורת — לא מנוחשת**, כדי לא לאשר תשלום עבור
הדייר הלא נכון. שווה לעבור על `audit_*.csv` אחרי כל הרצה ולוודא שאין
דילוגים על תשלומים אמיתיים.

## בדיקות

```bash
pytest tests/ -v
```

הבדיקות רצות על נתונים סינתטיים (`tests/fixtures/`) — לעולם לא על קובץ
בנק אמיתי.

## מבנה

```
automation/
  bank_parser.py   # פרסור אקסל הבנק לעסקאות מובנות
  matcher.py        # התאמת שם דייר/ספק בביטחון
  oxs_client.py      # אוטומציית Playwright מול OXS
  whatsapp.py        # שליחת הודעת אישור ב-WhatsApp Cloud API
  config.py           # טעינת .env
  main.py               # מריץ הכל, בונה לוג + audit trail
tests/                    # בדיקות + fixture סינתטי
```
