"use strict";

const themeToggle = document.querySelector("#theme-toggle");
function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    themeToggle.setAttribute("aria-pressed", String(theme === "dark"));
    themeToggle.textContent = theme === "dark" ? "Light theme" : "Dark theme";
}
let savedTheme = "dark";
try {
    const preference = localStorage.getItem("groots-theme");
    if (preference === "light" || preference === "dark") savedTheme = preference;
} catch { /* Storage can be unavailable for local files. */ }
applyTheme(savedTheme);
themeToggle.addEventListener("click", () => {
    const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(theme);
    try { localStorage.setItem("groots-theme", theme); } catch { /* Keep the current-page preference. */ }
});

let result, runs, latest, calls, sourceMap, messageMap, dates;
function loadSession(session) {
    if (!Array.isArray(session?.runs) || !Object.hasOwn(session, "result")) {
        throw new Error("Choose a Groots session.json file.");
    }
    const ledger = session.result?.ledger ?? {};
    const incomingCalls = session.runs.flatMap(run => run.calls ?? []);
    const incomingMessages = new Map(ledger.sources ?? []);
    const incomingDates = new Map(ledger.message_dates ?? []);
    result = session.result;
    runs = session.runs;
    latest = runs.at(-1);
    calls = incomingCalls;
    sourceMap = new Map(Object.entries(session.sources ?? {}));
    messageMap = incomingMessages;
    dates = incomingDates;
}

let currentSession = JSON.parse(document.querySelector("#session-data").content.textContent);
loadSession(currentSession);
const unavailable = "Unavailable";
const areaNames = ["venue", "schedule", "food", "judging", "budget"];
const sections = [["plan", "Plan"], ["trace", "Traces"], ["updates", "Updates"]];
const nav = document.querySelector("#nav");
const pages = document.querySelector("#pages");

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

function label(value) {
    const text = String(value).replaceAll("_", " ");
    return text[0]?.toUpperCase() + text.slice(1);
}

function display(value) {
    if (value === undefined || value === null) return unavailable;
    if (typeof value === "object") return JSON.stringify(value, null, 2);
    return String(value);
}

function pill(value) {
    const status = String(value ?? "UNKNOWN");
    return el("span", "pill " + status.toLowerCase(), status.toUpperCase());
}

function button(text, className, action) {
    const control = el("button", className, text);
    control.type = "button";
    control.addEventListener("click", action);
    return control;
}

function heading(page, title, subtitle, kicker) {
    const head = el("div", "lead");
    const group = el("div");
    if (kicker) group.append(el("p", "kicker", kicker));
    group.append(el("h1", "", title));
    if (subtitle) group.append(el("p", "muted", subtitle));
    head.append(group);
    page.append(head);
    return head;
}

function card(title, classes = "") {
    const panel = el("article", "card " + classes);
    panel.addEventListener("pointermove", event => {
        if (event.pointerType !== "mouse" || event.target.closest(".card") !== panel) return;
        const bounds = panel.getBoundingClientRect();
        const horizontal = (event.clientX - bounds.left) / bounds.width - 0.5;
        const vertical = (event.clientY - bounds.top) / bounds.height - 0.5;
        panel.style.setProperty("--tile-x", -vertical * 4 + "deg");
        panel.style.setProperty("--tile-y", horizontal * 4 + "deg");
    });
    panel.addEventListener("pointerleave", () => {
        panel.style.removeProperty("--tile-x");
        panel.style.removeProperty("--tile-y");
    });
    if (title) panel.append(el("h2", "", title));
    return panel;
}

function facts(values) {
    const list = el("dl");
    for (const [name, value] of values) {
        list.append(el("dt", "", name), el("dd", "", display(value)));
    }
    return list;
}

function details(title, makeBody) {
    const panel = el("details");
    panel.append(el("summary", "", title));
    panel.addEventListener("toggle", () => {
        if (panel.open && panel.childElementCount === 1) panel.append(makeBody());
    });
    return panel;
}

function message(run, id = run.source_id) {
    return messageMap.get(id) ?? sourceMap.get(id)?.text ??
        (id === run.source_id ? run.input_text : undefined);
}

function sourceMeta(id, text) {
    const sender = typeof text === "string" ? /^[ \t]*From:[ \t]*(.+)$/im.exec(text)?.[1] : undefined;
    return [sender, dates.get(id), id].filter(Boolean).join(" Â· ");
}

function tokenTotal(records, key) {
    if (!records.length) return "0";
    const known = records.filter(call => Number.isSafeInteger(call[key]) && call[key] >= 0);
    const sum = known.reduce((total, call) => total + call[key], 0);
    if (known.length !== records.length) {
        return known.length ? "Unavailable (" + sum.toLocaleString() + " reported)" : unavailable;
    }
    return sum.toLocaleString();
}

function areas(snapshot) {
    const plan = snapshot?.plan ?? snapshot?.areas;
    return plan?.areas ?? plan ?? {};
}

function planStatus(snapshot) {
    return snapshot?.status === "UNVERIFIED" ? "UNKNOWN" : (snapshot?.status ?? "UNKNOWN");
}

function quantity(value) {
    if ((typeof value !== "string" && typeof value !== "number") || String(value).trim() === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}

function budgetFigures(budget) {
    const total = quantity(budget?.total);
    const cap = quantity(budget?.cap);
    const currency = budget?.currency;
    const money = value => value === null || !currency ? unavailable :
        currency + " " + (typeof value === "number" ? value.toLocaleString(undefined, {maximumFractionDigits: 10}) : value);
    return {
        total: money(total === null ? null : budget.total),
        cap: money(cap === null ? null : budget.cap),
        remaining: money(total === null || cap === null ? null : cap - total),
        utilization: total === null || cap === null || cap <= 0 ? null : total / cap * 100,
    };
}

function runTitle(run) {
    return run.number === 1 ? "Initial run" : "Update " + (run.number - 1);
}

function table(columns, rows, className = "") {
    const wrapper = el("div", "table-scroll" + (className ? " " + className : ""));
    const grid = el("table", "data-table");
    const head = el("thead");
    const header = el("tr");
    columns.forEach((column, index) => {
        const cell = el("th", index === 0 && className === "diff" ? "path" : "", column);
        cell.scope = "col";
        header.append(cell);
    });
    head.append(header);
    const body = el("tbody");
    for (const item of rows) {
        const row = el("tr", item.changed ? "changed" : "");
        item.values.forEach(value => row.append(el("td", "", display(value))));
        body.append(row);
    }
    grid.append(head, body);
    wrapper.append(grid);
    return wrapper;
}

function chooseTime(value) {
    if (typeof value !== "string") return value;
    return value.replace("T", " ");
}

function barChart(title, values, units = "") {
    const panel = card(title);
    const known = values.map(([name, value]) => [name, quantity(value)]);
    const max = Math.max(1, ...known.map(([, value]) => value ?? 0));
    for (const [name, value] of known) {
        const row = el("div", "bar-row");
        const header = el("div", "row spread");
        header.append(el("span", "", name), el("span", "muted",
            value === null || value < 0 ? unavailable : value.toLocaleString() + units));
        row.append(header);
        if (value !== null && value >= 0) {
            const track = el("div", "bar-track");
            track.setAttribute("aria-hidden", "true");
            const fill = el("div", "bar-fill");
            fill.style.width = (value / max * 100) + "%";
            track.append(fill);
            row.append(track);
        }
        panel.append(row);
    }
    return panel;
}

function eventPlan(page) {
    const current = areas(result);
    const head = heading(page, "Event plan", latest?.status === "failed" ?
        "Saved plan before the latest run failed." : "Your latest event requirements and plan.");
    head.append(pill(planStatus(result)));
    const grid = el("div", "plan-grid");
    const venue = current.venue ?? {};
    const food = current.food ?? {};
    const judge = current.judging ?? {};
    const budget = current.budget ?? {};
    const schedule = current.schedule ?? {};
    const figures = budgetFigures(budget);

    const venueCard = card("Venue", "venue-panel");
    venueCard.append(facts([
        ["Selected venue", venue.option], ["Capacity", venue.capacity], ["Attendance", venue.people],
        ["Venue cost", venue.cost], ["Required features", venue.required_features?.join(", ")],
        ["Venue validation", venue.validation],
    ]));
    const scheduleCard = card("Schedule", "schedule-panel");
    scheduleCard.append(facts([
        ["Judging activity", schedule.activity], ["Starts", chooseTime(schedule.start)],
        ["Ends", chooseTime(schedule.end)], ["Event duration", schedule.duration_minutes == null ?
            undefined : schedule.duration_minutes + " minutes"],
    ]));
    const activities = Object.entries(schedule.activities ?? {});
    if (activities.length) {
        scheduleCard.append(table(["Activity", "Start", "End"],
            activities.map(([id, interval]) => ({
                values: [id, chooseTime(interval.start), chooseTime(interval.end)],
            }))));
    }
    const foodCard = card("Food", "food-panel");
    foodCard.append(facts([
        ["Selected package", food.item], ["Meals required", food.required], ["Meal quantity", food.quantity],
        ["Unit price", food.unit_price], ["Total meal cost", food.cost],
    ]));
    const judgingCard = card("Judging", "judging-panel");
    judgingCard.append(facts([
        ["Teams", judge.teams], ["Judges available", judge.available],
        ["Engaged judges", judge.engaged?.join(", ")], ["Capacity", judge.capacity],
    ]));
    if (judge.assignments?.length) {
        judgingCard.append(details("View assignments (" + judge.assignments.length + ")", () =>
            table(["Team", "Judge", "Start", "End"], judge.assignments.map(assignment => ({
                values: [assignment.team, assignment.judge, chooseTime(assignment.start), chooseTime(assignment.end)],
            })))));
    }
    const budgetCard = card("Budget", "budget-panel");
    budgetCard.append(facts([
        ["Total budget", figures.cap], ["Spent", figures.total], ["Remaining", figures.remaining],
        ["Committed costs", budget.committed], ["Constraint compliance", budget.validation],
    ]));
    if (Object.keys(budget.extras ?? {}).length) {
        budgetCard.append(details("Itemized extras", () => facts(Object.entries(budget.extras))));
    }
    const charts = el("div", "plan-charts");
    charts.append(
        barChart("Venue capacity", [["Attendance", venue.people], ["Capacity", venue.capacity]]),
        barChart("Meal coverage", [["Required", food.required], ["Planned", food.quantity]]),
        barChart("Budget usage", [["Spent", budget.total], ["Limit", budget.cap]],
            budget.currency ? " " + budget.currency : ""),
    );
    page.append(charts);
    grid.append(scheduleCard, venueCard, foodCard, judgingCard, budgetCard);
    page.append(grid);
    const issues = result?.plan?.issues ?? [];
    if (issues.length) {
        const notes = card("Validation notes");
        const list = el("ul", "list");
        issues.forEach(issue => list.append(el("li", "", issue)));
        notes.append(list);
        page.append(notes);
    }
}
function paged(items, size, renderItems) {
    const container = el("div", "stack");
    let index = 0;
    function draw(direction) {
        container.replaceChildren(renderItems(items.slice(index, index + size)));
        if (items.length <= size) return;
        const controls = el("div", "row");
        const previous = button("Previous", "secondary", () => { index -= size; draw("previous"); });
        previous.disabled = index === 0;
        const next = button("Next", "secondary", () => { index += size; draw("next"); });
        next.disabled = index + size >= items.length;
        controls.append(previous, el("span", "muted", (index + 1) + "â€“" +
            Math.min(index + size, items.length) + " of " + items.length), next);
        container.append(controls);
        if (direction === "previous") (previous.disabled ? next : previous).focus();
        if (direction === "next") (next.disabled ? previous : next).focus();
    }
    draw();
    return container;
}

function runSources(run) {
    const ids = new Set();
    for (const decision of run.decisions ?? []) {
        if (decision.source?.startsWith(run.source_id + ":") || decision.source === run.source_id) {
            ids.add(decision.source);
        }
    }
    return ids.size ? [...ids] : [run.source_id];
}

function runInput(run) {
    const group = el("div", "stack");
    for (const id of runSources(run)) {
        const text = message(run, id);
        group.append(el("p", "muted mono", sourceMeta(id, text) || unavailable),
            el("pre", "message", text === "" ? "(Empty input)" : text ?? unavailable));
    }
    return group;
}

function decisionList(run) {
    const panel = el("div", "stack");
    if (!run.decisions?.length) panel.append(el("p", "muted", "No decisions recorded."));
    for (const decision of run.decisions ?? []) {
        const group = el("div");
        group.append(pill(decision.outcome), el("p", "", decision.reason ?? unavailable));
        if (decision.source) group.append(el("p", "muted mono", decision.source));
        panel.append(group);
    }
    if (run.error) panel.append(el("p", "", run.error));
    return panel;
}

function flatten(snapshot) {
    const output = new Map();
    function visit(value, path) {
        if (value && typeof value === "object" && Object.keys(value).length) {
            for (const [key, child] of Object.entries(value)) visit(child, [...path, key]);
        } else {
            output.set(JSON.stringify(path), value);
        }
    }
    if (snapshot?.plan) visit(snapshot.plan, []);
    if (snapshot?.status) output.set(JSON.stringify(["status"]), snapshot.status);
    return output;
}

function compare(before, after) {
    const panel = card("Before and after");
    if (before === undefined || after === undefined) {
        panel.append(el("p", "muted", "A historical snapshot is unavailable. This run predates snapshot recording."));
        for (const [name, snapshot] of [["Before", before], ["After", after]]) {
            if (snapshot?.plan) panel.append(details(name + " Â· Available snapshot",
                () => el("pre", "", display(snapshot.plan))));
        }
        return panel;
    }
    if (before === null) panel.append(el("p", "muted", "There was no saved plan before this run."));
    if (after === null) panel.append(el("p", "muted", "This run left no saved plan."));
    const previous = flatten(before);
    const following = flatten(after);
    const keys = new Set([...previous.keys(), ...following.keys()]);
    const rows = [...keys].map(key => {
        const old = previous.get(key);
        const next = following.get(key);
        return {
            changed: JSON.stringify(old) !== JSON.stringify(next),
            values: [JSON.parse(key).map(label).join(" / "), old, next],
        };
    });
    if (!rows.length) return panel;
    const changed = rows.filter(row => row.changed).length;
    panel.append(el("p", "muted", changed ? changed + " changed fields" : "No plan fields changed"),
        paged(rows, 40, group => table(["Field", "Before", "After"], group, "diff")));
    return panel;
}

function updates(page) {
    heading(page, "Updates", "Follow incoming messages and the decisions they triggered.");
    const toolbar = el("div", "row spread");
    const filterLabel = el("label", "", "Decision ");
    const filter = el("select");
    for (const [value, title] of [
        ["all", "All decisions"], ["accepted", "Accepted"], ["rejected", "Rejected"],
        ["ignored", "Ignored / stale"], ["unresolved", "Unresolved"],
    ]) {
        const option = el("option", "", title);
        option.value = value;
        filter.append(option);
    }
    filterLabel.append(filter);
    const count = el("p", "muted");
    count.setAttribute("aria-live", "polite");
    toolbar.append(filterLabel, count);
    const content = el("div", "stack");
    const rows = runs.flatMap(run => run.decisions?.length ?
        run.decisions.map(decision => ({run, decision})) : [{run, decision: null}]);

    function updateList() {
        const visible = rows.filter(({decision}) => filter.value === "all" ||
            (filter.value === "ignored" && decision?.outcome === "superseded") ||
            decision?.outcome === filter.value);
        count.textContent = visible.length + (visible.length === 1 ? " entry" : " entries");
        content.replaceChildren(paged(visible, 25, items => {
            const group = el("div", "stack");
            if (!items.length) group.append(card("No matching updates"));
            for (const {run, decision} of items) {
                const panel = card(null);
                const head = el("div", "row spread");
                head.append(el("h2", "", runTitle(run)), pill(decision?.outcome ?? run.status));
                const id = decision?.source ?? run.source_id;
                const text = message(run, id);
                panel.append(head, el("p", "muted mono", sourceMeta(id, text) || unavailable),
                    el("p", "", decision?.reason ?? run.error ?? "No decision recorded."),
                    el("p", "muted", "Affected areas: " + (run.affected_areas?.join(", ") || unavailable)),
                    details("Original message", () => el("pre", "message",
                        text === "" ? "(Empty input)" : text ?? unavailable)));
                panel.append(details("Plan changes", () => compare(run.before, run.after)));
                group.append(panel);
            }
            return group;
        }));
    }
    filter.addEventListener("change", updateList);
    page.append(toolbar, content);
    updateList();
}

function trace(page) {
    heading(page, "Traces", "Messages, API calls, responses, and token usage.");
    const summary = card("Cumulative usage", "cyan");
    summary.append(facts([
        ["Attempted calls", calls.length], ["Input tokens", tokenTotal(calls, "prompt_tokens")],
        ["Output tokens", tokenTotal(calls, "completion_tokens")],
        ["Total tokens", tokenTotal(calls, "total_tokens")],
    ]));
    const attempts = runs.flatMap(run => (run.calls ?? []).map(call => ({run, call})));
    const listing = paged(attempts, 25, items => {
        const group = el("div", "stack");
        if (!items.length) group.append(card("No model calls recorded"));
        for (const {run, call} of items) {
            const panel = card(null);
            const entry = details("Model call " + call.number + " Â· " + call.area + " Â· " + call.model, () => {
                const body = el("div", "stack");
                body.append(details("Original message", () => runInput(run)));
                const requested = call.configured_model ?? call.input?.model ?? call.requested_model;
                const returned = call.output?.model ?? call.returned_model ?? call.reported_model;
                body.append(facts([
                    ["Run", runTitle(run)], ["Area tag", call.area], ["Requested model", requested],
                    ["Returned model", returned], ["Input tokens", call.prompt_tokens],
                    ["Output tokens", call.completion_tokens], ["Total tokens", call.total_tokens],
                    ["Latency", call.elapsed_seconds == null ? undefined : call.elapsed_seconds + " s"],
                    ["Error", call.error ?? "None recorded"],
                ]));
                for (const [title, value] of [["Full request payload", call.input], ["Full response", call.output]]) {
                    body.append(details(title, () => el("pre", "", display(value))));
                }
                return body;
            });
            panel.append(entry);
            group.append(panel);
        }
        return group;
    });
    page.append(summary, listing);
}

const renderers = {plan: eventPlan, updates, trace};
const tabs = new Map();

function activate(id, moveFocus = false) {
    for (const [key, {tab, panel}] of tabs) {
        const selected = id === key;
        tab.setAttribute("aria-selected", String(selected));
        tab.tabIndex = selected ? 0 : -1;
        panel.hidden = !selected;
    }
    const {tab, panel} = tabs.get(id);
    if (!panel.firstChild) renderers[id](panel);
    if (moveFocus) tab.focus();
}

sections.forEach(([id, title], index) => {
    const tab = button(title, "", () => activate(id));
    tab.id = "tab-" + id;
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-controls", "panel-" + id);
    tab.addEventListener("keydown", event => {
        let next;
        if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % sections.length;
        if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (index - 1 + sections.length) % sections.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = sections.length - 1;
        if (next !== undefined) {
            event.preventDefault();
            activate(sections[next][0], true);
        }
    });
    const panel = el("section", "page");
    panel.id = "panel-" + id;
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", tab.id);
    panel.tabIndex = 0;
    nav.append(tab);
    pages.append(panel);
    tabs.set(id, {tab, panel});
});

activate("plan");

// The offline dashboard opens saved planner results.
const upload = document.querySelector("#session-upload");
const uploadStatus = document.querySelector("#upload-status");
upload.addEventListener("change", async () => {
    const file = upload.files[0];
    if (!file) return;
    const refresh = () => {
        for (const {panel} of tabs.values()) panel.replaceChildren();
        activate("plan");
    };
    try {
        const session = JSON.parse(await file.text());
        loadSession(session);
        refresh();
        currentSession = session;
        uploadStatus.textContent = file.name;
    } catch {
        loadSession(currentSession);
        refresh();
        uploadStatus.textContent = "Could not open this file. Choose a Groots session.json.";
    } finally {
        upload.value = "";
    }
});
