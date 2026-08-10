# Workout Planner

A mobile-first browser workout planner and tracker. The web app stores routines, workout history, and PB data in the browser with `localStorage`, and can sync signed-in users through Supabase.

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
- Sign in with Google and sync each user's data to their own Supabase row
- Start from a sign-in/guest landing screen; guest mode uses browser storage only
- Creating new routines requires Google sign-in
- Installable PWA shell with offline caching

The previous Python desktop app is still included for reference, but active development is now focused on the browser version.

## Supabase

The live app is configured for the `Workout Planner` Supabase project. The database schema is mirrored in `supabase/schema.sql`. Only the publishable browser key is stored in this repo; Google OAuth client secrets stay in Supabase/Google Cloud.
