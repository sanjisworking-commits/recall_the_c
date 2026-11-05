# Schedules prototype sources

These four files must sit in the same folder. The `.dc.html` files load `./support.js` and `import('./schedules-text.js')` at runtime.

| File | Role |
|------|------|
| [Recall the C - Playground Desktop.dc.html](Recall%20the%20C%20-%20Playground%20Desktop.dc.html) | Desktop Browse + Schedule screens |
| [Recall the C - Playground.dc.html](Recall%20the%20C%20-%20Playground.dc.html) | Phone (390 px) Browse + Schedule screens |
| [support.js](support.js) | Prototype runtime |
| [schedules-text.js](schedules-text.js) | Official Schedule extract (`export const SCHEDULES`) |

`python scripts/build_schedules_json.py` copies that extract into `src/constitution_memorizer/web/schedules.json` for the FastAPI Browse pages.
