(() => {
  "use strict";

  const STORAGE_KEY = "workoutPlanner.web.v1";
  const USER_STORAGE_PREFIX = `${STORAGE_KEY}.user.`;
  const GUEST_MODE_KEY = `${STORAGE_KEY}.guestMode`;
  const APP_VERSION = "1.1.11";
  const TODAY = new Date().toISOString().slice(0, 10);
  const SUPABASE_TABLE = "workout_planner_data";

  const PLATE_DENOMINATIONS = [45, 35, 25, 10, 5, 2.5];
  const DEFAULT_WEIGHT_OFFSET = "45";
  const NEW_EXERCISE_OFFSET = "0";

  const INITIAL_DATA = {
    settings: { always_on_top: false },
    selected_routine: "Push Day",
    routines: {
      "Push Day": [
        { exercise: "Incline Barbell Press", weight: "125", reps: "3x8", weight_offset: "45", track_pb: false },
        { exercise: "Seated Shoulder Press", weight: "67.5", reps: "3x10", weight_offset: "45", track_pb: false },
        { exercise: "Cable Chest Fly", weight: "40", reps: "3x8", weight_offset: "20", track_pb: false },
        { exercise: "Cable Lateral Raise", weight: "15", reps: "3x8", weight_offset: "0", track_pb: false },
        { exercise: "Cable Tricep Pushdown", weight: "45", reps: "3x10", weight_offset: "0", track_pb: false },
        { exercise: "Overhead Cable Tricep Extension", weight: "40", reps: "2x15", weight_offset: "0", track_pb: false },
      ],
      "Pull Day": [
        { exercise: "Barbell Row", weight: "100", reps: "3x8", weight_offset: "45", track_pb: false },
        { exercise: "Lat Pulldown", weight: "100", reps: "3x6", weight_offset: "45", track_pb: false },
        { exercise: "Cable Row 1 Arm", weight: "40", reps: "3x8", weight_offset: "0", track_pb: false },
        { exercise: "Face Pulls", weight: "40", reps: "3x12", weight_offset: "0", track_pb: false },
        { exercise: "Preacher Curl", weight: "30", reps: "3x10", weight_offset: "0", track_pb: false },
        { exercise: "Hammer Curl 1 Arm", weight: "15", reps: "2x10", weight_offset: "0", track_pb: false },
      ],
    },
    routine_logs: [],
  };

  const app = document.getElementById("app");
  const importFile = document.getElementById("import-file");
  const toast = document.getElementById("toast");
  const cloudConfig = window.WORKOUT_SUPABASE || {};
  const supabaseClient =
    window.supabase && cloudConfig.url && cloudConfig.anonKey
      ? window.supabase.createClient(cloudConfig.url, cloudConfig.anonKey, {
          auth: {
            autoRefreshToken: true,
            detectSessionInUrl: true,
            persistSession: true,
          },
        })
      : null;

  let authSession = null;
  let state = loadState();
  let currentPage = "routine";
  let editMode = false;
  let editSnapshot = null;
  let guestMode = localStorage.getItem(GUEST_MODE_KEY) === "true";
  let authReady = !supabaseClient;
  let cloudSaveTimer = null;
  let cloudLoadActive = false;
  let cloudStatus = supabaseClient ? "Cloud ready" : "Local only";
  let cloudDatabaseFull = false;
  let selectedHistory = new Set();
  let dataSelection = {
    kind: "routine",
    value: state.selected_routine,
  };
  let toastTimer = null;
  let confirmResolver = null;
  let longPressTimer = null;

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/\n/g, "&#10;");
  }

  function iconSvg(name) {
    const icons = {
      edit:
        '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4l11-11-4-4L4 16v4z"></path><path d="M14 6l4 4"></path></svg>',
      cancel:
        '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12"></path><path d="M18 6L6 18"></path></svg>',
      trash:
        '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16"></path><path d="M9 7V5h6v2"></path><path d="M7 7l1 13h8l1-13"></path><path d="M10 11v5"></path><path d="M14 11v5"></path></svg>',
      up:
        '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5"></path><path d="M5 12l7-7 7 7"></path></svg>',
      down:
        '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14"></path><path d="M19 12l-7 7-7-7"></path></svg>',
    };
    return icons[name] || "";
  }

  function boolFromData(value) {
    if (typeof value === "string") {
      return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
    }
    return Boolean(value);
  }

  function formatWeight(value) {
    if (value === "" || value === null || value === undefined) return "";
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return String(value);
    const rounded = Math.round(parsed * 10) / 10;
    return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
  }

  function formatWhole(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? String(Math.round(parsed)) : "0";
  }

  function isTwoPointFiveStep(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return false;
    return Math.abs(parsed / 2.5 - Math.round(parsed / 2.5)) < 0.00001;
  }

  function isValidWeight(value) {
    if (String(value).trim() === "") return false;
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed >= 0 && isTwoPointFiveStep(parsed);
  }

  function isValidOffset(value) {
    const text = String(value ?? "").trim();
    if (!text) return true;
    const parsed = Number(text);
    return Number.isFinite(parsed) && parsed >= 0 && isTwoPointFiveStep(parsed);
  }

  function normalizeExercise(row = {}) {
    const weight = row.weight ?? row.target_weight ?? "";
    return {
      exercise: String(row.exercise || "New Exercise"),
      weight: weight === "" ? "" : formatWeight(weight),
      reps: String(row.reps ?? row.target_reps ?? ""),
      weight_offset: String(row.weight_offset ?? DEFAULT_WEIGHT_OFFSET),
      track_pb: boolFromData(row.track_pb),
    };
  }

  function routinesFromLegacy(data) {
    const groups = data.groups || INITIAL_DATA.routines;
    const routines = {};
    Object.entries(groups).forEach(([name, rows]) => {
      routines[name] = Array.isArray(rows) ? rows.map(normalizeExercise) : [];
    });
    return Object.keys(routines).length ? routines : clone(INITIAL_DATA.routines);
  }

  function logsFromLegacy(data) {
    const byKey = new Map();
    (data.sets || []).forEach((item) => {
      const routine = String(item.routine || item.exercise_group || "Imported");
      const logDate = String(item.date || TODAY);
      const key = `${logDate}::${routine}`;
      if (!byKey.has(key)) byKey.set(key, { date: logDate, routine, exercises: [], pb_entries: [] });
      byKey.get(key).exercises.push(normalizeExercise(item));
    });
    return Array.from(byKey.values());
  }

  function normalizeLog(log = {}) {
    const exercises = Array.isArray(log.exercises) ? log.exercises.map(normalizeExercise) : [];
    const pbEntries = Array.isArray(log.pb_entries)
      ? log.pb_entries.map((entry) => ({
          exercise: String(entry.exercise || ""),
          weight: formatWeight(entry.weight ?? ""),
          reps: String(entry.reps ?? ""),
        }))
      : [];
    return {
      date: String(log.date || TODAY),
      routine: String(log.routine || "Workout"),
      exercises,
      pb_entries: pbEntries,
    };
  }

  function normalizeData(input) {
    const source = input && typeof input === "object" ? input : {};
    const routines = source.routines ? clone(source.routines) : routinesFromLegacy(source);
    Object.keys(routines).forEach((name) => {
      routines[name] = Array.isArray(routines[name]) ? routines[name].map(normalizeExercise) : [];
      if (!routines[name].length) {
        routines[name] = [{ exercise: "New Exercise", weight: "", reps: "", weight_offset: NEW_EXERCISE_OFFSET, track_pb: false }];
      }
    });

    const routineLogs = source.routine_logs
      ? source.routine_logs.map(normalizeLog)
      : logsFromLegacy(source).map(normalizeLog);
    const selected = String(source.selected_routine || source.selected_group || Object.keys(routines)[0] || "Push Day");
    return {
      settings: { always_on_top: boolFromData(source.settings?.always_on_top) },
      selected_routine: routines[selected] ? selected : Object.keys(routines)[0],
      routines,
      routine_logs: routineLogs,
    };
  }

  function userStorageKey(userId) {
    return `${USER_STORAGE_PREFIX}${userId}`;
  }

  function currentStorageKey() {
    return authSession?.user?.id ? userStorageKey(authSession.user.id) : STORAGE_KEY;
  }

  function loadStoredState(key) {
    try {
      const stored = localStorage.getItem(key);
      if (stored) return normalizeData(JSON.parse(stored));
    } catch (_error) {
      localStorage.removeItem(key);
    }
    return null;
  }

  function loadState(key = STORAGE_KEY) {
    const stored = loadStoredState(key);
    if (stored) return stored;
    return normalizeData(INITIAL_DATA);
  }

  function saveState(options = {}) {
    localStorage.setItem(currentStorageKey(), JSON.stringify(state));
    if (options.cloud !== false) queueCloudSave();
  }

  function applyLoadedState(nextState) {
    state = normalizeData(nextState);
    dataSelection = { kind: "routine", value: state.selected_routine };
    selectedHistory = new Set();
  }

  function cloudUserLabel() {
    if (!authSession?.user) return "";
    return authSession.user.user_metadata?.full_name || authSession.user.email || "Google user";
  }

  function hasCloudIdentity() {
    return Boolean(authSession?.user);
  }

  function canCreateRoutines() {
    return hasCloudIdentity();
  }

  function canEnterApp() {
    return hasCloudIdentity() || guestMode;
  }

  function localStorageStatus() {
    return guestMode ? "Guest mode<br>Browser storage only" : "Not signed in<br>Browser storage only";
  }

  function authRedirectUrl() {
    return `${window.location.origin}${window.location.pathname}`;
  }

  async function signInWithGoogle() {
    if (!supabaseClient) {
      showToast("Cloud sync is not configured.");
      return;
    }
    guestMode = false;
    localStorage.removeItem(GUEST_MODE_KEY);
    cloudStatus = "Opening Google...";
    updateMenuStatus();
    const { error } = await supabaseClient.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: authRedirectUrl() },
    });
    if (error) {
      cloudStatus = "Sign in failed";
      updateMenuStatus();
      showToast("Google sign in failed.");
    }
  }

  function enterGuestMode() {
    guestMode = true;
    localStorage.setItem(GUEST_MODE_KEY, "true");
    cloudStatus = "Browser storage only";
    applyLoadedState(loadState(STORAGE_KEY));
    currentPage = "routine";
    render();
    showToast("Guest mode saves to this browser only.");
  }

  function leaveGuestMode() {
    guestMode = false;
    localStorage.removeItem(GUEST_MODE_KEY);
    cloudStatus = "Browser storage only";
    render();
  }

  function cloudMenu() {
    if (!supabaseClient) {
      return '<button class="menu-item menu-status" type="button" disabled>Cloud sync unavailable</button>';
    }
    if (!authSession) {
      return `
        <button class="menu-item" type="button" data-action="sign-in-google">Sign in with Google</button>
        ${
          guestMode
            ? '<button class="menu-item" type="button" data-action="leave-guest">Leave Guest Mode</button>'
            : '<button class="menu-item" type="button" data-action="guest-sign-in">Guest Sign In</button>'
        }
        <button class="menu-item menu-status" type="button" disabled>${localStorageStatus()}</button>
      `;
    }
    return `
      <button class="menu-item" type="button" data-action="sync-cloud">Sync Now</button>
      <button class="menu-item" type="button" data-action="sign-out-google">Sign out</button>
      <button class="menu-item menu-status" type="button" disabled>${escapeHtml(cloudUserLabel())}<br>${escapeHtml(cloudStatus)}</button>
    `;
  }

  function isDatabaseFullError(error) {
    const status = String(error?.status || error?.code || "");
    const message = String(error?.message || error?.details || error || "").toLowerCase();
    return (
      ["402", "413", "507", "53100", "53200", "53300", "53400", "54000"].includes(status) ||
      /quota|limit|exceeded|database.*full|storage.*full|disk|insufficient resources|row is too big/.test(message)
    );
  }

  function queueCloudSave() {
    if (!supabaseClient || !authSession || cloudLoadActive || cloudDatabaseFull) return;
    window.clearTimeout(cloudSaveTimer);
    cloudSaveTimer = window.setTimeout(() => saveCloudData({ quiet: true }), 650);
  }

  async function saveCloudData({ quiet = false } = {}) {
    if (!supabaseClient || !authSession) return { ok: false, skipped: true };
    if (cloudDatabaseFull) {
      if (!quiet) showToast("Database is full. Saved on this device only.");
      return { ok: false, databaseFull: true };
    }
    window.clearTimeout(cloudSaveTimer);
    cloudStatus = "Syncing...";
    try {
      const payload = normalizeData(state);
      const { error } = await supabaseClient.from(SUPABASE_TABLE).upsert(
        {
          user_id: authSession.user.id,
          payload,
        },
        { onConflict: "user_id" }
      );
      if (error) throw error;
      cloudStatus = "Synced";
      return { ok: true };
    } catch (error) {
      if (isDatabaseFullError(error)) {
        cloudDatabaseFull = true;
        cloudStatus = "Database full";
        showToast("Database is full. Saved on this device only.");
        return { ok: false, databaseFull: true };
      }
      cloudStatus = "Cloud sync failed";
      if (!quiet) showToast("Saved on this device. Cloud sync failed.");
      return { ok: false, error };
    } finally {
      updateMenuStatus();
    }
  }

  async function loadCloudData() {
    if (!supabaseClient || !authSession) return;
    cloudLoadActive = true;
    cloudStatus = "Loading cloud...";
    updateMenuStatus();
    try {
      const { data, error } = await supabaseClient
        .from(SUPABASE_TABLE)
        .select("payload")
        .eq("user_id", authSession.user.id)
        .maybeSingle();
      if (error) throw error;
      if (data?.payload) {
        applyLoadedState(data.payload);
        saveState({ cloud: false });
        cloudStatus = "Synced";
      } else {
        const userLocalState = loadStoredState(userStorageKey(authSession.user.id));
        applyLoadedState(userLocalState || INITIAL_DATA);
        saveState({ cloud: false });
        cloudLoadActive = false;
        await saveCloudData({ quiet: true });
        cloudLoadActive = true;
      }
    } catch (error) {
      cloudStatus = isDatabaseFullError(error) ? "Database full" : "Cloud sync failed";
      if (isDatabaseFullError(error)) cloudDatabaseFull = true;
      showToast(cloudDatabaseFull ? "Database is full. Saved on this device only." : "Cloud data unavailable.");
    } finally {
      cloudLoadActive = false;
      render();
    }
  }

  function updateMenuStatus() {
    const statusNode = app.querySelector(".menu-status");
    if (statusNode) {
      statusNode.innerHTML = authSession
        ? `${escapeHtml(cloudUserLabel())}<br>${escapeHtml(cloudStatus)}`
        : escapeHtml(cloudStatus);
    }
  }

  async function initCloudAuth() {
    if (!supabaseClient) return;
    try {
      const { data } = await supabaseClient.auth.getSession();
      authSession = data.session;
      authReady = true;
      if (authSession) {
        guestMode = false;
        localStorage.removeItem(GUEST_MODE_KEY);
        cloudStatus = "Signed in";
        await loadCloudData();
      } else {
        cloudStatus = "Browser storage only";
        render();
      }
      supabaseClient.auth.onAuthStateChange((_event, session) => {
        authSession = session;
        authReady = true;
        cloudDatabaseFull = false;
        if (session) {
          guestMode = false;
          localStorage.removeItem(GUEST_MODE_KEY);
          cloudStatus = "Signed in";
          loadCloudData();
        } else {
          cloudStatus = "Browser storage only";
          window.clearTimeout(cloudSaveTimer);
          applyLoadedState(loadState(STORAGE_KEY));
          render();
        }
      });
    } catch (_error) {
      cloudStatus = "Cloud sync failed";
      render();
    }
  }

  function routineNames() {
    return Object.keys(state.routines).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  }

  function currentRoutine() {
    if (!state.routines[state.selected_routine]) {
      state.selected_routine = routineNames()[0];
      saveState();
    }
    return state.selected_routine;
  }

  function currentRows() {
    return state.routines[currentRoutine()] || [];
  }

  function setPage(page) {
    if (!canEnterApp()) {
      render();
      return;
    }
    if (page === "new" && !canCreateRoutines()) {
      currentPage = "routine";
      closeEditMode(false);
      selectedHistory = new Set();
      render();
      showToast("Sign in with Google to create routines.");
      return;
    }
    currentPage = page;
    if (page !== "routine") closeEditMode(false);
    selectedHistory = new Set();
    render();
  }

  function showToast(message) {
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add("visible");
    toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 1800);
  }

  function confirmDialog(title, message, okText = "OK") {
    const backdrop = document.getElementById("confirm-backdrop");
    const titleNode = document.getElementById("confirm-title");
    const messageNode = document.getElementById("confirm-message");
    const okButton = document.getElementById("confirm-ok");
    const cancelButton = document.getElementById("confirm-cancel");
    titleNode.textContent = title;
    messageNode.textContent = message;
    okButton.textContent = okText;
    backdrop.hidden = false;
    okButton.focus();
    return new Promise((resolve) => {
      confirmResolver = resolve;
      const finish = (result) => {
        backdrop.hidden = true;
        okButton.onclick = null;
        cancelButton.onclick = null;
        confirmResolver = null;
        resolve(result);
      };
      okButton.onclick = () => finish(true);
      cancelButton.onclick = () => finish(false);
      backdrop.onclick = (event) => {
        if (event.target === backdrop) finish(false);
      };
    });
  }

  function closeEditMode(saveChanges) {
    if (!editMode) return;
    if (!saveChanges && editSnapshot) {
      state.routines[state.selected_routine] = editSnapshot;
      saveState();
    }
    editMode = false;
    editSnapshot = null;
  }

  function shell(title, body) {
    return `
      <section class="screen">
        <header class="topbar">
          <h1>${escapeHtml(title)}</h1>
          <button class="hamburger" type="button" data-action="toggle-menu" aria-label="Menu"><span></span></button>
        </header>
        <nav class="app-menu" data-menu hidden>
          <button class="menu-item" type="button" data-nav="routine">Home</button>
          <button class="menu-item" type="button" data-nav="new" ${canCreateRoutines() ? "" : "disabled"}>New Routine</button>
          <div class="menu-separator"></div>
          <button class="menu-item" type="button" data-nav="history">History</button>
          <button class="menu-item" type="button" data-nav="data">Data</button>
          <button class="menu-item" type="button" data-nav="settings">Settings</button>
          <div class="menu-separator"></div>
          ${cloudMenu()}
          <div class="menu-separator"></div>
          <button class="menu-item" type="button" disabled>Version ${escapeHtml(APP_VERSION)}</button>
        </nav>
        <main class="page-body">${body}</main>
      </section>
    `;
  }

  function authShell(body) {
    return `
      <section class="screen auth-screen">
        <main class="auth-body">${body}</main>
      </section>
    `;
  }

  function renderAuthGate() {
    if (!authReady) {
      return authShell(`
        <section class="auth-panel">
          <img class="auth-logo" src="icons/icon.svg" alt="">
          <h1>Workout Planner</h1>
          <p class="auth-copy">Checking sign in...</p>
        </section>
      `);
    }
    return authShell(`
      <section class="auth-panel">
        <img class="auth-logo" src="icons/icon.svg" alt="">
        <h1>Workout Planner</h1>
        <div class="auth-actions">
          <button class="btn btn-primary" type="button" data-action="sign-in-google">Sign in with Google</button>
          <button class="btn btn-secondary" type="button" data-action="guest-sign-in">Continue as Guest</button>
        </div>
        <p class="auth-copy">Cloud storage requires Google sign in.</p>
        <p class="auth-version">Version ${escapeHtml(APP_VERSION)}</p>
      </section>
    `);
  }

  function render() {
    if (!canEnterApp()) {
      closeEditMode(false);
      app.innerHTML = renderAuthGate();
      bindAuthGate();
      return;
    }
    const title = currentPage === "routine" ? "Workout Planner" : titleForPage(currentPage);
    app.innerHTML = shell(title, bodyForPage(currentPage));
    bindShell();
    if (currentPage === "routine") bindRoutinePage();
    if (currentPage === "new") bindNewRoutinePage();
    if (currentPage === "history") bindHistoryPage();
    if (currentPage === "data") bindDataPage();
    if (currentPage === "settings") bindSettingsPage();
  }

  function bindAuthGate() {
    const signIn = app.querySelector("[data-action='sign-in-google']");
    if (signIn) signIn.addEventListener("click", signInWithGoogle);
    const guestSignIn = app.querySelector("[data-action='guest-sign-in']");
    if (guestSignIn) guestSignIn.addEventListener("click", enterGuestMode);
  }

  function titleForPage(page) {
    return {
      new: "New Routine",
      history: "History",
      data: "Data",
      settings: "Settings",
    }[page] || "Workout Planner";
  }

  function bodyForPage(page) {
    if (page === "new") return renderNewRoutinePage();
    if (page === "history") return renderHistoryPage();
    if (page === "data") return renderDataPage();
    if (page === "settings") return renderSettingsPage();
    return renderRoutinePage();
  }

  function bindShell() {
    const menu = app.querySelector("[data-menu]");
    app.querySelector("[data-action='toggle-menu']").addEventListener("click", () => {
      menu.hidden = !menu.hidden;
    });
    app.querySelectorAll("[data-nav]").forEach((button) => {
      button.addEventListener("click", () => setPage(button.dataset.nav));
    });
    const signIn = app.querySelector("[data-action='sign-in-google']");
    if (signIn) signIn.addEventListener("click", signInWithGoogle);
    const guestSignIn = app.querySelector("[data-action='guest-sign-in']");
    if (guestSignIn) guestSignIn.addEventListener("click", enterGuestMode);
    const leaveGuest = app.querySelector("[data-action='leave-guest']");
    if (leaveGuest) leaveGuest.addEventListener("click", leaveGuestMode);
    const signOut = app.querySelector("[data-action='sign-out-google']");
    if (signOut) {
      signOut.addEventListener("click", async () => {
        if (!supabaseClient) return;
        await supabaseClient.auth.signOut();
        authSession = null;
        guestMode = false;
        localStorage.removeItem(GUEST_MODE_KEY);
        cloudStatus = "Browser storage only";
        cloudDatabaseFull = false;
        window.clearTimeout(cloudSaveTimer);
        applyLoadedState(loadState(STORAGE_KEY));
        render();
      });
    }
    const sync = app.querySelector("[data-action='sync-cloud']");
    if (sync) {
      sync.addEventListener("click", async () => {
        const result = await saveCloudData({ quiet: false });
        if (result.ok) showToast("Cloud sync complete.");
      });
    }
  }

  function renderRoutinePage() {
    const rows = currentRows();
    return `
      <section class="routine-page">
        <div>
          <p class="section-label">Routine</p>
          <div class="routine-control-row">
            <div class="routine-selector">
              <button class="select-like" type="button" data-action="toggle-routine-menu">${escapeHtml(currentRoutine())}</button>
              <div class="routine-menu" data-routine-menu hidden>
                ${routineNames()
                  .map(
                    (name) =>
                      `<button class="routine-option ${name === currentRoutine() ? "active" : ""}" type="button" data-routine="${escapeAttr(name)}">${escapeHtml(name)}</button>`
                  )
                  .join("")}
              </div>
            </div>
            <div class="routine-toolbar">
              <button class="btn btn-secondary routine-tool" type="button" data-action="toggle-edit" aria-label="${editMode ? "Cancel edit" : "Edit routine"}" title="${editMode ? "Cancel" : "Edit Routine"}">${iconSvg(editMode ? "cancel" : "edit")}</button>
              <button class="btn btn-danger routine-tool" type="button" data-action="delete-current-routine" aria-label="Delete routine" title="Delete Routine">${iconSvg("trash")}</button>
            </div>
          </div>
        </div>
        <div class="routine-list" data-routine-list>
          ${rows.map((row, index) => renderExerciseCard(row, index)).join("")}
        </div>
        <div class="bottom-actions">
          ${editMode ? '<button class="btn btn-secondary" type="button" data-action="add-exercise">Add Exercise</button>' : ""}
          <button class="btn btn-primary" type="button" data-action="save-routine">${editMode ? "Save Changes" : "Save Workout"}</button>
        </div>
        <div class="scroll-float" data-scroll-float></div>
      </section>
    `;
  }

  function renderExerciseCard(row, index) {
    const editable = editMode;
    const pbEditable = !editable && row.track_pb;
    return `
      <article class="exercise-card" data-index="${index}">
        <div class="exercise-side">
          ${renderPlate(row)}
          ${
            editable
              ? `<div class="move-controls">
                  <button class="move-btn" type="button" data-action="move-exercise" data-direction="up" data-index="${index}" aria-label="Move exercise up" title="Move up" ${index === 0 ? "disabled" : ""}>${iconSvg("up")}</button>
                  <button class="move-btn" type="button" data-action="move-exercise" data-direction="down" data-index="${index}" aria-label="Move exercise down" title="Move down" ${index === currentRows().length - 1 ? "disabled" : ""}>${iconSvg("down")}</button>
                </div>`
              : ""
          }
        </div>
        <div class="exercise-detail">
          <div class="card-title-row">
            ${
              editable
                ? '<div class="edit-actions"><button class="delete-mini" type="button" data-action="delete-exercise" data-index="' +
                  index +
                  '">X</button><button class="pb-btn ' +
                  (row.track_pb ? "active" : "") +
                  '" type="button" data-action="toggle-pb" data-index="' +
                  index +
                  '">PB</button></div>'
                : '<h2 class="exercise-title">' +
                  escapeHtml(row.exercise) +
                  '</h2><button class="pb-btn ' +
                  (row.track_pb ? "active" : "") +
                  '" type="button" data-action="toggle-pb" data-index="' +
                  index +
                  '">PB</button>'
            }
          </div>
          ${
            editable
              ? `<input class="text-input full-row" data-field="exercise" data-index="${index}" value="${escapeAttr(row.exercise)}">`
              : ""
          }
          <div class="field-label">Weight</div>
          <div class="field-label">Reps</div>
          ${fieldOrBox(row, index, "weight", "lbs", editable || pbEditable)}
          ${fieldOrBox(row, index, "reps", "", editable || pbEditable)}
          ${
            editable
              ? `<div class="field-label full-row">Set Weight Offset</div>
                 <input class="text-input full-row" data-field="weight_offset" data-index="${index}" value="${escapeAttr(row.weight_offset)}">`
              : ""
          }
        </div>
      </article>
    `;
  }

  function fieldOrBox(row, index, field, suffix, editable) {
    if (editable) {
      return `<input class="text-input" data-field="${field}" data-index="${index}" value="${escapeAttr(row[field])}">`;
    }
    return `
      <div class="value-box">
        <span class="value-main">${escapeHtml(row[field])}</span>
        ${suffix ? `<span class="value-suffix">${escapeHtml(suffix)}</span>` : ""}
      </div>
    `;
  }

  function plateCountsForWeight(weightValue, offsetValue) {
    const weight = Number(weightValue);
    const offset = Number(String(offsetValue ?? "").trim() || 0);
    if (!Number.isFinite(weight) || !Number.isFinite(offset) || offset < 0) {
      return { sideWeight: 0, counts: PLATE_DENOMINATIONS.map((plate) => [plate, 0]) };
    }
    const roundedTotal = Math.floor(weight / 5) * 5;
    let sideWeight = Math.max((roundedTotal - offset) / 2, 0);
    let remaining = sideWeight;
    const counts = PLATE_DENOMINATIONS.map((plate) => {
      const count = Math.floor((remaining + 0.00001) / plate);
      remaining = Math.round((remaining - plate * count) * 100) / 100;
      return [plate, count];
    });
    return { sideWeight, counts };
  }

  function renderPlate(row) {
    const { sideWeight, counts } = plateCountsForWeight(row.weight, row.weight_offset);
    const plates = [];
    counts.forEach(([plate, count]) => {
      for (let i = 0; i < count; i += 1) plates.push(plate);
    });
    plates.sort((a, b) => b - a);
    const cardWidth = 150;
    const centerY = 64;
    const shaftWidth = 16;
    const stopWidth = 7;
    const tailWidth = 24;
    const plateGap = 6;
    const dimensions = plateDimensions();
    const stackWidth = plates.reduce((total, plate) => total + dimensions[plate][0], 0) + plateGap * Math.max(plates.length - 1, 0);
    const emptyStackWidth = 52;
    const loadedWidth = shaftWidth + stopWidth + (plates.length ? stackWidth + tailWidth : emptyStackWidth);
    const startX = Math.max(8, Math.round((cardWidth - loadedWidth) / 2));
    const stopX = startX + shaftWidth;
    const sleeveStart = stopX + stopWidth;
    const sleeveEnd = plates.length ? sleeveStart + stackWidth + tailWidth : stopX + stopWidth + emptyStackWidth;
    let nextPlateX = sleeveStart;

    const plateMarkup = plates
      .map((plate, index) => {
        const [width, height] = dimensions[plate];
        const x = nextPlateX;
        nextPlateX += width + plateGap;
        return renderPlatePiece(plate, index, x, centerY, width, height);
      })
      .join("");

    return `
      <div class="plate-card" data-plate>
        <div class="plate-title">Barbels: ${escapeHtml(formatWeight(sideWeight))}lb</div>
        <div class="barbell-stack">
          <div class="barbell-part shaft-left" style="left:${startX}px;top:${centerY - 2}px;width:${shaftWidth}px"></div>
          <div class="barbell-part plate-stop" style="left:${stopX}px;top:${centerY - 14}px;width:${stopWidth}px;height:28px"></div>
          <div class="barbell-part sleeve" style="left:${sleeveStart}px;top:${centerY - 5}px;width:${Math.max(0, sleeveEnd - sleeveStart)}px;height:10px"></div>
          ${plateMarkup}
        </div>
      </div>
    `;
  }

  function plateDimensions() {
    return {
      45: [18, 80],
      35: [16, 68],
      25: [14, 58],
      10: [11, 44],
      5: [9, 34],
      2.5: [8, 26],
    };
  }

  function renderPlatePiece(plate, index, x, centerY, width, height) {
    const shade = index % 2 === 0 ? "light" : "mid";
    const top = centerY - height / 2;
    return `
      <div class="plate ${shade}" style="left:${x}px;top:${top}px;width:${width}px;height:${height}px"></div>
      <div class="plate-label ${shade}" style="left:${x - 5}px;top:106px;width:${width + 10}px">${escapeHtml(formatWeight(plate))}</div>
    `;
  }

  function bindRoutinePage() {
    const routineMenu = app.querySelector("[data-routine-menu]");
    app.querySelector("[data-action='toggle-routine-menu']").addEventListener("click", () => {
      routineMenu.hidden = !routineMenu.hidden;
    });
    app.querySelectorAll("[data-routine]").forEach((button) => {
      const selectRoutine = () => {
        closeEditMode(false);
        state.selected_routine = button.dataset.routine;
        dataSelection = { kind: "routine", value: state.selected_routine };
        saveState();
        render();
      };
      button.addEventListener("click", selectRoutine);
      button.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        deleteRoutine(button.dataset.routine);
      });
      button.addEventListener("pointerdown", () => {
        window.clearTimeout(longPressTimer);
        longPressTimer = window.setTimeout(() => deleteRoutine(button.dataset.routine), 650);
      });
      button.addEventListener("pointerup", () => window.clearTimeout(longPressTimer));
      button.addEventListener("pointerleave", () => window.clearTimeout(longPressTimer));
      button.addEventListener("pointercancel", () => window.clearTimeout(longPressTimer));
    });

    app.querySelector("[data-action='save-routine']").addEventListener("click", saveRoutineButton);
    app.querySelector("[data-action='toggle-edit']").addEventListener("click", toggleEditMode);
    app.querySelector("[data-action='delete-current-routine']").addEventListener("click", () => deleteRoutine(currentRoutine()));
    const addButton = app.querySelector("[data-action='add-exercise']");
    if (addButton) addButton.addEventListener("click", addExercise);

    app.querySelectorAll("[data-field]").forEach((input) => {
      input.addEventListener("input", () => {
        const row = currentRows()[Number(input.dataset.index)];
        row[input.dataset.field] = input.value;
        saveState();
        const card = input.closest(".exercise-card");
        const plate = card?.querySelector("[data-plate]");
        if (plate && ["weight", "weight_offset"].includes(input.dataset.field)) {
          plate.outerHTML = renderPlate(row);
        }
      });
    });

    app.querySelectorAll("[data-action='toggle-pb']").forEach((button) => {
      button.addEventListener("click", () => {
        const row = currentRows()[Number(button.dataset.index)];
        row.track_pb = !row.track_pb;
        saveState();
        render();
      });
    });

    app.querySelectorAll("[data-action='delete-exercise']").forEach((button) => {
      button.addEventListener("click", () => deleteExercise(Number(button.dataset.index)));
    });

    app.querySelectorAll("[data-action='move-exercise']").forEach((button) => {
      button.addEventListener("click", () => moveExercise(Number(button.dataset.index), button.dataset.direction));
    });

    const list = app.querySelector("[data-routine-list]");
    const float = app.querySelector("[data-scroll-float]");
    bindFloatingScroll(list, float);
  }

  function moveExercise(index, direction) {
    const rows = currentRows();
    const targetIndex = direction === "up" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= rows.length) return;
    [rows[index], rows[targetIndex]] = [rows[targetIndex], rows[index]];
    saveState();
    render();
  }

  function toggleEditMode() {
    if (currentPage !== "routine") {
      currentPage = "routine";
    }
    if (editMode) {
      closeEditMode(false);
    } else {
      editSnapshot = clone(currentRows());
      editMode = true;
    }
    render();
  }

  async function saveRoutineButton() {
    if (!validateRows()) return;
    if (editMode) {
      editMode = false;
      editSnapshot = null;
      saveState();
      render();
      if (!hasCloudIdentity()) {
        showToast(`${currentRoutine()} was updated in this browser.`);
        return;
      }
      const result = await saveCloudData({ quiet: true });
      showToast(result.databaseFull ? "Database is full. Saved on this device only." : `${currentRoutine()} was updated.`);
      return;
    }
    const ok = await confirmDialog("Save workout", `Save ${currentRoutine()} for ${TODAY}?`, "Save");
    if (!ok) return;
    const exercises = currentRows().map((row) => ({
      exercise: row.exercise.trim(),
      weight: formatWeight(row.weight),
      reps: row.reps.trim(),
      weight_offset: formatWeight(row.weight_offset || NEW_EXERCISE_OFFSET),
      track_pb: Boolean(row.track_pb),
    }));
    const pbEntries = currentRows()
      .filter((row) => row.track_pb)
      .map((row) => ({
        exercise: row.exercise.trim(),
        weight: formatWeight(row.weight),
        reps: row.reps.trim(),
    }));
    state.routine_logs.push({ date: TODAY, routine: currentRoutine(), exercises, pb_entries: pbEntries });
    saveState();
    if (!hasCloudIdentity()) {
      showToast(`${currentRoutine()} was saved to this browser.`);
      return;
    }
    const result = await saveCloudData({ quiet: true });
    showToast(result.databaseFull ? "Database is full. Saved on this device only." : `${currentRoutine()} was saved for ${TODAY}.`);
  }

  function validateRows() {
    for (const row of currentRows()) {
      if (!row.exercise.trim() || !row.reps.trim() || !isValidWeight(row.weight) || !isValidOffset(row.weight_offset)) {
        showToast("Each exercise needs a name, reps, a weight, and a valid offset.");
        return false;
      }
    }
    return true;
  }

  function addExercise() {
    currentRows().push({
      exercise: "New Exercise",
      weight: "",
      reps: "",
      weight_offset: NEW_EXERCISE_OFFSET,
      track_pb: false,
    });
    saveState();
    render();
  }

  async function deleteExercise(index) {
    if (currentRows().length <= 1) {
      showToast("Each routine needs at least one exercise.");
      return;
    }
    const ok = await confirmDialog("Delete exercise", `Delete ${currentRows()[index].exercise}?`, "Delete");
    if (!ok) return;
    currentRows().splice(index, 1);
    saveState();
    render();
  }

  async function deleteRoutine(routine) {
    if (routineNames().length <= 1) {
      showToast("You need at least one routine.");
      return;
    }
    const ok = await confirmDialog("Delete routine", `Delete ${routine}?`, "Delete");
    if (!ok) return;
    delete state.routines[routine];
    if (state.selected_routine === routine) {
      state.selected_routine = routineNames()[0];
      dataSelection = { kind: "routine", value: state.selected_routine };
    }
    closeEditMode(false);
    saveState();
    render();
  }

  function renderNewRoutinePage() {
    if (!canCreateRoutines()) {
      return `
        <section class="form-page">
          <p class="section-label">Google Sign In Required</p>
          <div class="status">New routines need a Google account. Workouts still save to this browser in guest mode.</div>
          <button class="btn btn-primary" type="button" data-action="sign-in-google">Sign in with Google</button>
        </section>
      `;
    }
    return `
      <section class="form-page">
        <p class="section-label">Routine Name</p>
        <input class="text-input" data-new-routine-name autocomplete="off">
        <div class="status" data-status></div>
        <button class="btn btn-primary" type="button" data-action="create-routine">Create Routine</button>
      </section>
    `;
  }

  function bindNewRoutinePage() {
    if (!canCreateRoutines()) {
      const signIn = app.querySelector("[data-action='sign-in-google']");
      if (signIn) signIn.addEventListener("click", signInWithGoogle);
      return;
    }
    const input = app.querySelector("[data-new-routine-name]");
    const create = app.querySelector("[data-action='create-routine']");
    const status = app.querySelector("[data-status]");
    const createRoutine = () => {
      const name = input.value.trim();
      if (!name) {
        status.textContent = "Enter a routine name.";
        return;
      }
      if (state.routines[name]) {
        status.textContent = "That routine already exists.";
        return;
      }
      state.routines[name] = [{ exercise: "New Exercise", weight: "", reps: "", weight_offset: NEW_EXERCISE_OFFSET, track_pb: false }];
      state.selected_routine = name;
      dataSelection = { kind: "routine", value: name };
      editMode = true;
      editSnapshot = clone(state.routines[name]);
      saveState();
      currentPage = "routine";
      render();
    };
    create.addEventListener("click", createRoutine);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") createRoutine();
    });
    input.focus();
  }

  function renderSettingsPage() {
    return `
      <section class="settings-page">
        <label class="checkbox-row">
          <button class="switch ${state.settings.always_on_top ? "on" : ""}" type="button" data-action="toggle-top"></button>
          <span>Always On Top</span>
        </label>
      </section>
    `;
  }

  function bindSettingsPage() {
    app.querySelector("[data-action='toggle-top']").addEventListener("click", () => {
      state.settings.always_on_top = !state.settings.always_on_top;
      saveState();
      render();
    });
  }

  function renderHistoryPage() {
    const rows = state.routine_logs
      .map((log, index) => ({ log, index }))
      .reverse()
      .map(({ log, index }) => {
        const selected = selectedHistory.has(index);
        return `
          <tr class="history-row ${selected ? "selected" : ""}" data-history-index="${index}">
            <td>${escapeHtml(log.date)}</td>
            <td>${escapeHtml(log.routine)}</td>
            <td>${escapeHtml(log.exercises.length)}</td>
          </tr>
        `;
      })
      .join("");
    return `
      <section class="history-page">
        <div class="btn-row">
          <button class="btn btn-secondary" type="button" data-action="export-data">Export All</button>
          <button class="btn btn-secondary" type="button" data-action="import-data">Import</button>
          <button class="btn btn-secondary" type="button" data-action="select-all">Select All</button>
          <button class="btn btn-secondary" type="button" data-action="deselect-all">Deselect All</button>
        </div>
        <div class="history-list">
          <table>
            <thead><tr><th>Date</th><th>Routine</th><th>Exercises</th></tr></thead>
            <tbody>${rows || '<tr><td colspan="3" class="muted">No saved workouts yet.</td></tr>'}</tbody>
          </table>
        </div>
        <button class="btn btn-danger" type="button" data-action="delete-history">Delete</button>
      </section>
    `;
  }

  function bindHistoryPage() {
    app.querySelector("[data-action='export-data']").addEventListener("click", exportData);
    app.querySelector("[data-action='import-data']").addEventListener("click", () => importFile.click());
    app.querySelector("[data-action='select-all']").addEventListener("click", () => {
      selectedHistory = new Set(state.routine_logs.map((_log, index) => index));
      render();
    });
    app.querySelector("[data-action='deselect-all']").addEventListener("click", () => {
      selectedHistory = new Set();
      render();
    });
    app.querySelector("[data-action='delete-history']").addEventListener("click", deleteHistory);
    app.querySelectorAll("[data-history-index]").forEach((row) => {
      row.addEventListener("click", () => {
        const index = Number(row.dataset.historyIndex);
        if (selectedHistory.has(index)) selectedHistory.delete(index);
        else selectedHistory.add(index);
        render();
      });
    });
  }

  function exportData() {
    const payload = {
      app: "Workout Planner",
      exported_on: TODAY,
      ...state,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `workout_planner_data_${TODAY}.json`;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
  }

  async function deleteHistory() {
    if (!selectedHistory.size) {
      showToast("Select saved workouts to delete.");
      return;
    }
    const count = selectedHistory.size;
    const ok = await confirmDialog("Delete history", `Delete ${count} saved workout${count === 1 ? "" : "s"}?`, "Delete");
    if (!ok) return;
    state.routine_logs = state.routine_logs.filter((_log, index) => !selectedHistory.has(index));
    selectedHistory = new Set();
    saveState();
    render();
    showToast(`Deleted ${count} history entr${count === 1 ? "y" : "ies"}.`);
  }

  function importData(payload) {
    const incoming = normalizeData(payload);
    let routineCount = 0;
    Object.entries(incoming.routines).forEach(([name, rows]) => {
      if (!state.routines[name]) {
        state.routines[name] = rows;
        routineCount += 1;
      }
    });

    const dates = new Set(state.routine_logs.map((log) => String(log.date)));
    let logCount = 0;
    let skipped = 0;
    incoming.routine_logs.forEach((log) => {
      if (!log.date || dates.has(String(log.date))) {
        skipped += 1;
        return;
      }
      state.routine_logs.push(log);
      dates.add(String(log.date));
      logCount += 1;
    });
    saveState();
    render();
    showToast(`Imported ${routineCount} routines and ${logCount} history entries. Skipped ${skipped}.`);
  }

  importFile.addEventListener("change", async () => {
    const file = importFile.files?.[0];
    if (!file) return;
    try {
      const payload = JSON.parse(await file.text());
      importData(payload);
    } catch (_error) {
      showToast("Import failed. Select a valid JSON file.");
    } finally {
      importFile.value = "";
    }
  });

  function exercisePoints() {
    const points = [];
    state.routine_logs.forEach((log) => {
      log.exercises.forEach((item) => {
        points.push({
          date: log.date,
          routine: log.routine,
          exercise: item.exercise,
          weight: item.weight,
          reps: item.reps,
          numericWeight: Number(item.weight) || 0,
          tooltip: `${item.exercise}\nWeight: ${item.weight}\nReps: ${item.reps}`,
        });
      });
    });
    return points.sort((a, b) => String(b.date).localeCompare(String(a.date)));
  }

  function pbPoints() {
    const points = [];
    state.routine_logs.forEach((log) => {
      let entries = Array.isArray(log.pb_entries) ? log.pb_entries : [];
      if (!entries.length) entries = log.exercises.filter((item) => item.track_pb);
      entries.forEach((item) => {
        if (!item.exercise) return;
        points.push({
          date: log.date,
          routine: log.routine,
          exercise: item.exercise,
          weight: item.weight,
          reps: item.reps,
          numericWeight: Number(item.weight) || 0,
          tooltip: `${item.exercise}\nPB Weight: ${item.weight}\nPB Reps: ${item.reps}`,
        });
      });
    });
    return points.sort((a, b) => String(b.date).localeCompare(String(a.date)));
  }

  function parseRepsForSummary(value) {
    const text = String(value || "").trim().toLowerCase().replace(/x/g, "x").replace(/[–—]/g, "-");
    const match = text.match(/(\d+)\s*(?:x|sets?\s*x?)\s*(\d+)(?:\s*-\s*(\d+))?/);
    if (match) {
      const sets = Number(match[1]);
      const low = Number(match[2]);
      const high = match[3] ? Number(match[3]) : low;
      return { sets, reps: (low + high) / 2 };
    }
    const single = text.match(/\d+/);
    return single ? { sets: 1, reps: Number(single[0]) } : { sets: 0, reps: 0 };
  }

  function summarizeRoutineLog(log) {
    let totalSets = 0;
    let totalReps = 0;
    let totalWeight = 0;
    log.exercises.forEach((item) => {
      const weight = Number(item.weight) || 0;
      const parsed = parseRepsForSummary(item.reps);
      if (parsed.sets <= 0 || parsed.reps <= 0) return;
      totalSets += parsed.sets;
      totalReps += parsed.sets * parsed.reps;
      totalWeight += weight * parsed.sets * parsed.reps;
    });
    return {
      date: log.date,
      routine: log.routine,
      totalWeight,
      totalSets,
      averageReps: totalSets ? totalReps / totalSets : 0,
    };
  }

  function routineSummaries(routine) {
    return state.routine_logs
      .filter((log) => log.routine === routine)
      .map(summarizeRoutineLog)
      .sort((a, b) => String(b.date).localeCompare(String(a.date)));
  }

  function dataGroups() {
    const routines = routineNames();
    const exerciseSet = new Set(exercisePoints().map((point) => point.exercise));
    Object.values(state.routines).forEach((rows) => rows.forEach((row) => exerciseSet.add(row.exercise)));
    const routineExercises = {};
    const assigned = new Set();
    routines.forEach((routine) => {
      const names = new Set((state.routines[routine] || []).map((row) => row.exercise).filter(Boolean));
      state.routine_logs
        .filter((log) => log.routine === routine)
        .forEach((log) => log.exercises.forEach((item) => names.add(item.exercise)));
      routineExercises[routine] = Array.from(names).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
      routineExercises[routine].forEach((name) => assigned.add(name));
    });
    const other = Array.from(exerciseSet)
      .filter((name) => name && !assigned.has(name))
      .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
    return { routines, routineExercises, other };
  }

  function ensureDataSelection(groups) {
    if (dataSelection.kind === "routine" && groups.routines.includes(dataSelection.value)) return;
    if (dataSelection.kind === "exercise") {
      const allExercises = [...Object.values(groups.routineExercises).flat(), ...groups.other];
      if (allExercises.includes(dataSelection.value)) return;
    }
    if (groups.routines.length) dataSelection = { kind: "routine", value: groups.routines[0] };
    else if (groups.other.length) dataSelection = { kind: "exercise", value: groups.other[0] };
    else dataSelection = { kind: "", value: "" };
  }

  function renderDataPage() {
    const groups = dataGroups();
    ensureDataSelection(groups);
    const chartPoints = selectedChartPoints();
    const historyPoints = selectedPbHistory();
    return `
      <section class="data-page">
        <div class="data-selector">
          <button class="data-selector-button" type="button" data-action="toggle-data-menu">${escapeHtml(dataSelection.value || "Select Data")}</button>
          <div class="data-menu" data-data-menu hidden>
            ${groups.routines
              .map(
                (routine) => `
                  <button class="data-option group" type="button" data-kind="routine" data-value="${escapeAttr(routine)}">${escapeHtml(routine)}</button>
                  ${groups.routineExercises[routine]
                    .map(
                      (exercise) =>
                        `<button class="data-option child" type="button" data-kind="exercise" data-value="${escapeAttr(exercise)}">${escapeHtml(exercise)}</button>`
                    )
                    .join("")}
                `
              )
              .join("")}
            <button class="data-option group" type="button" data-action="noop">Other</button>
            ${groups.other
              .map(
                (exercise) =>
                  `<button class="data-option child" type="button" data-kind="exercise" data-value="${escapeAttr(exercise)}">${escapeHtml(exercise)}</button>`
              )
              .join("")}
          </div>
        </div>
        ${renderTrendChart(chartPoints)}
        <p class="section-label">PB History</p>
        <div class="history-list">
          <table>
            <colgroup>
              <col class="history-date">
              <col class="history-exercise">
              <col class="history-weight">
              <col class="history-reps">
            </colgroup>
            <thead><tr><th>Date</th><th>Exercise</th><th>Weight</th><th>Reps</th></tr></thead>
            <tbody>
              ${
                historyPoints.length
                  ? historyPoints
                      .map(
                        (point) =>
                          `<tr><td>${escapeHtml(point.date)}</td><td>${escapeHtml(point.exercise)}</td><td>${escapeHtml(formatWeight(point.weight))}</td><td>${escapeHtml(point.reps)}</td></tr>`
                      )
                      .join("")
                  : '<tr><td colspan="4" class="muted">No PB history yet.</td></tr>'
              }
            </tbody>
          </table>
        </div>
      </section>
    `;
  }

  function selectedChartPoints() {
    if (dataSelection.kind === "routine") {
      return routineSummaries(dataSelection.value).map((summary) => ({
        date: summary.date,
        label: summary.routine,
        value: summary.totalWeight,
        tooltip: `${summary.routine}\nTotal Moved: ${formatWeight(summary.totalWeight)}\nSets: ${summary.totalSets}, Avg Reps: ${formatWhole(summary.averageReps)}`,
      }));
    }
    if (dataSelection.kind === "exercise") {
      return exercisePoints()
        .filter((point) => point.exercise === dataSelection.value)
        .map((point) => ({
          date: point.date,
          label: point.exercise,
          value: point.numericWeight,
          tooltip: point.tooltip,
        }));
    }
    return [];
  }

  function selectedPbHistory() {
    const points = pbPoints();
    if (dataSelection.kind === "routine") return points.filter((point) => point.routine === dataSelection.value);
    if (dataSelection.kind === "exercise") return points.filter((point) => point.exercise === dataSelection.value);
    return points;
  }

  function renderTrendChart(points) {
    const usable = points.filter((point) => Number(point.value) > 0).slice().reverse();
    if (usable.length < 2) {
      return '<div class="chart-panel"><div class="chart-message">Save this item twice to see a trend.</div></div>';
    }
    const width = 360;
    const height = 190;
    const padX = 38;
    const padY = 28;
    const values = usable.map((point) => Number(point.value));
    let low = Math.min(...values) * 0.92;
    let high = Math.max(...values) * 1.08;
    if (low === high) high += 1;
    const plotW = width - padX * 2;
    const plotH = height - padY * 2;
    const coords = usable.map((point, index) => {
      const x = padX + (plotW * index) / (usable.length - 1);
      const y = padY + plotH * (1 - (Number(point.value) - low) / (high - low));
      return { x, y, point };
    });
    const path = coords.map((coord, index) => `${index ? "L" : "M"} ${coord.x.toFixed(2)} ${coord.y.toFixed(2)}`).join(" ");
    const grid = [0, 1, 2, 3]
      .map((index) => {
        const y = padY + (plotH * index) / 3;
        return `<line x1="${padX}" y1="${y}" x2="${width - padX}" y2="${y}" stroke="#202a3a" stroke-width="1"></line>`;
      })
      .join("");
    const circles = coords
      .map(
        ({ x, y, point }) =>
          `<circle class="chart-point" cx="${x}" cy="${y}" r="4" fill="#38bdf8" data-tip="${escapeAttr(point.tooltip)}"></circle>`
      )
      .join("");
    return `
      <div class="chart-panel" data-chart-panel>
        <svg class="trend-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
          ${grid}
          <path d="${path}" fill="none" stroke="#38bdf8" stroke-width="3"></path>
          ${circles}
          <text x="${padX}" y="18" fill="#8ea0b8" font-size="10">${escapeHtml(formatWeight(values[0]))} lb</text>
          <text x="${width - padX}" y="18" fill="#eef5ff" font-size="10" text-anchor="end">${escapeHtml(formatWeight(values[values.length - 1]))} lb</text>
        </svg>
        <div class="chart-tooltip" data-chart-tooltip hidden></div>
      </div>
    `;
  }

  function bindDataPage() {
    const menuButton = app.querySelector("[data-action='toggle-data-menu']");
    const menu = app.querySelector("[data-data-menu]");
    menuButton.addEventListener("click", () => {
      menu.hidden = !menu.hidden;
    });
    app.querySelectorAll("[data-kind]").forEach((button) => {
      button.addEventListener("click", () => {
        dataSelection = { kind: button.dataset.kind, value: button.dataset.value };
        render();
      });
    });
    app.querySelectorAll("[data-action='noop']").forEach((button) => {
      button.addEventListener("click", () => {
        menu.hidden = true;
      });
    });

    const panel = app.querySelector("[data-chart-panel]");
    if (panel) {
      const tooltip = panel.querySelector("[data-chart-tooltip]");
      panel.querySelectorAll(".chart-point").forEach((point) => {
        const show = (event) => {
          tooltip.textContent = point.dataset.tip;
          tooltip.hidden = false;
          const panelBox = panel.getBoundingClientRect();
          const tipBox = tooltip.getBoundingClientRect();
          let left = event.clientX - panelBox.left + 12;
          let top = event.clientY - panelBox.top - tipBox.height - 12;
          if (left + tipBox.width + 8 > panelBox.width) left = panelBox.width - tipBox.width - 8;
          if (top < 8) top = event.clientY - panelBox.top + 12;
          if (top + tipBox.height + 8 > panelBox.height) top = panelBox.height - tipBox.height - 8;
          tooltip.style.left = `${Math.max(8, left)}px`;
          tooltip.style.top = `${Math.max(8, top)}px`;
        };
        point.addEventListener("pointerenter", show);
        point.addEventListener("pointermove", show);
        point.addEventListener("click", show);
      });
      panel.addEventListener("pointerleave", () => {
        tooltip.hidden = true;
      });
    }
  }

  function bindFloatingScroll(list, float) {
    if (!list || !float) return;
    let fadeTimer = null;
    const update = () => {
      if (list.scrollHeight <= list.clientHeight + 2) return;
      const box = list.getBoundingClientRect();
      const ratio = list.clientHeight / list.scrollHeight;
      const topRatio = list.scrollTop / (list.scrollHeight - list.clientHeight);
      const thumbHeight = Math.max(30, box.height * ratio);
      float.style.height = `${thumbHeight}px`;
      float.style.top = `${box.top + (box.height - thumbHeight) * topRatio}px`;
      float.classList.add("visible");
      window.clearTimeout(fadeTimer);
      fadeTimer = window.setTimeout(() => float.classList.remove("visible"), 380);
    };
    list.addEventListener("scroll", update, { passive: true });
  }

  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-menu]") && !event.target.closest("[data-action='toggle-menu']")) {
      const menu = app.querySelector("[data-menu]");
      if (menu) menu.hidden = true;
    }
    if (!event.target.closest(".data-selector")) {
      const dataMenu = app.querySelector("[data-data-menu]");
      if (dataMenu) dataMenu.hidden = true;
    }
    if (!event.target.closest(".routine-selector")) {
      const routineMenu = app.querySelector("[data-routine-menu]");
      if (routineMenu) routineMenu.hidden = true;
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      const backdrop = document.getElementById("confirm-backdrop");
      if (!backdrop.hidden) document.getElementById("confirm-cancel").click();
      const menu = app.querySelector("[data-menu]");
      if (menu) menu.hidden = true;
      const dataMenu = app.querySelector("[data-data-menu]");
      if (dataMenu) dataMenu.hidden = true;
      const routineMenu = app.querySelector("[data-routine-menu]");
      if (routineMenu) routineMenu.hidden = true;
    }
  });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("sw.js").catch(() => {});
    });
  }

  render();
  initCloudAuth();
})();
