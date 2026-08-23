# Memo SWEP MVP

## Start

Use `/swep` in Telegram.

The menu contains:

- 🧠 Reconstruct Previous SWEP
- 📘 Fill My Logbook
- ➕ Capture Today's Experience
- 📸 Add Evidence
- 📊 My Progress

## Historical flow

1. Student chooses a date.
2. Memo resolves the known 2026 phase:
   - 27–28 July: initial orientation
   - 29 July–17 August: department rotation
   - 18–21 August: second-phase orientation
   - 22 August onward: specialized project
3. For rotation dates, student selects the building.
4. Student supplies a short personal memory.
5. Memo retrieves shared context and generates a structured draft.
6. Memo asks at most one high-value personalization question when needed.
7. Memo regenerates the draft and saves it in the student's persistent Telegram user data.
8. Student can continue to the next day.

## Data boundary

`data/swep/building_context.json` is shared context. It must never be treated as proof of individual participation.

`data/swep/logbook_requirements.json` defines the MVP output fields.

`data/swep/personalization_rules.json` limits the follow-up questions.

`data/swep/generation_context.json` contains the grounding and anti-hallucination rules.

## Current MVP limitations

- Rotation timetable mapping is not yet automatic; the student selects the building for a rotation date.
- The 18–21 August orientation currently relies on the student's memory because day-specific orientation notes are not yet a separate context dataset.
- Evidence is stored by Memo's existing capture pipeline but is not yet automatically linked to a specific logbook field.
- Group/subgroup context is not yet part of generation.
- Saved SWEP entries currently use Telegram's persistent `user_data`; a database model should be added after the tomorrow-MVP launch.
