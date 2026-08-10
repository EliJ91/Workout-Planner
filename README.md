# Workout Planner

A mobile-first browser workout planner and tracker. The web app stores routines, workout history, and PB data in the browser with `localStorage`.

## Run

Open `index.html` in a browser, or serve the folder locally:

```powershell
python -m http.server 8080
```

Then open `http://localhost:8080`.

## Features

- Create, edit, delete, and select workout routines
- Save workout entries with confirmation
- Track weight, reps, set weight offsets, and PB-marked exercises
- View routine and exercise trend graphs
- View PB History beneath the graph
- Export all browser data to JSON
- Import desktop or browser JSON data into browser storage
- Installable PWA shell with offline caching

The previous Python desktop app is still included for reference, but active development is now focused on the browser version.
