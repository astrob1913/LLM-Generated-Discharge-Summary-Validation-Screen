# Validating LLM-generated discharge summaries against the clinical record

An interactive screen that sets a language-model-generated hospital discharge summary beside the
ward notes it was written from, and asks a clinician to decide, line by line, whether the record
supports each statement.

- **Live page:** https://astrob1913.github.io/LLM-Generated-Discharge-Summary-Validation-Screen/
- **Companion notes:** https://astrob1913.github.io/LLM-Generated-Discharge-Summary-Validation-Screen/guide.html

## All clinical data here is synthetic

The patient does not exist. The record was generated for this project, and the name, NHS number and
date of birth are invented. **No real person, record or NHS number appears anywhere in this
repository.**

## What this is, and is not

This is a research prototype built for an MSc Data Science dissertation at City St George's,
University of London. It is **not a medical device and not for clinical use.**

It runs entirely in the browser. There is no server, no account and no tracking. Anything a reviewer
types is stored in their own browser and reaches nobody else.

## Repository contents

| File | What it is |
|---|---|
| `index.html` | The validation screen. Self-contained; no build step. |
| `guide.html` | Companion notes explaining the screen for anyone using it. |
| `test_screen.js` | The 73 automated checks of the screen (see *Running the checks* below). |
| `data/episode_0219fb71.json` | The processed record of the patient on the screen, which the checks compare every record card against. |
| `data/*.csv` | The three synthetic source files: patients, admissions and clinical notes. |
| `Bhuvanesi_Barua_Source_Code.txt` | All the code written for the project in one file, as submitted with the dissertation. |
| `Literature_Matrix_and_Design_Log.xlsx` | The literature matrix, error taxonomy and design log kept during the project. |

## Running the checks

The screen is held to 73 automated checks. They open it in a browser and confirm, among other
things, that every record card matches its note word for word, that each statement shows the
evidence it declares and that a reviewer's decisions survive a reload.

You need Node.js, version 18 or later (https://nodejs.org).

1. Download this repository (green **Code** button, then **Download ZIP**) and unzip it.
2. Open a terminal in the unzipped folder, the one that contains `test_screen.js`.
   On Windows, type `cmd` in the File Explorer address bar of that folder and press Enter.
3. Install Playwright and its browser. This is needed only once:

   ```
   npm install playwright
   npx playwright install chromium
   ```

4. Run the checks:

   ```
   node test_screen.js
   ```

The run takes about a minute and ends with `73 passed, 0 failed`. The run itself needs no internet
connection.

## Device requirement

The screen needs a browser window at least 820px wide and 560px tall — a laptop, desktop, or tablet
held upright. Smaller windows get a card asking the reader to open the link on a computer. This is
deliberate: the design depends on a claim and its evidence being visible at the same moment, which a
phone cannot do.

## Status

Work in progress, ahead of dissertation submission. Not released for reuse.

