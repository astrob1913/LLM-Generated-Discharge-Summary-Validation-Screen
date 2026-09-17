# Validating LLM-generated discharge summaries against the clinical record

An interactive screen that sets a language-model-generated hospital discharge summary beside the
ward notes it was written from, and asks a clinician to decide, line by line, whether the record
supports each statement.

**Live page:** https://astrob1913.github.io/LLM-Generated-Discharge-Summary-Validation-Screen/
**Companion notes:** https://USERNAME.github.io/REPONAME/guide.html

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

## Device requirement

The screen needs a browser window at least 820px wide and 560px tall — a laptop, desktop, or tablet
held upright. Smaller windows get a card asking the reader to open the link on a computer. This is
deliberate: the design depends on a claim and its evidence being visible at the same moment, which a
phone cannot do.

## Status

Work in progress, ahead of dissertation submission. Not released for reuse.
