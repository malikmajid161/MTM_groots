const planner = document.querySelector("#planner");
const plannerForm = document.querySelector("#planner-form");
const plannerInput = document.querySelector("#planner-input");
const plannerFile = document.querySelector("#planner-file");
const plannerRun = document.querySelector("#planner-run");
const plannerStatus = document.querySelector("#planner-status");
const plannerExports = document.querySelector("#planner-exports");
let uploadedMessageText;

function showPlannerStatus(message, error = false) {
    plannerStatus.textContent = message;
    plannerStatus.dataset.error = String(error);
}

function updatePlannerControls(session) {
    plannerRun.textContent = session.result ? "Apply update" : "Generate plan";
    plannerInput.placeholder = session.result ? "Paste a new message to update the saved plan" : "Paste your message pack here";
    plannerExports.hidden = !session.runs.length;
}
function busy(value) {
    for (const control of [plannerRun, plannerInput, plannerFile]) control.disabled = value;
    plannerForm.setAttribute("aria-busy", String(value));
}
async function plannerRequest(path, payload) {
    const response = await fetch(path, {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "The planner request failed.");
    return data;
}

planner.open = !currentSession.result;
updatePlannerControls(currentSession);
document.querySelector("#view-mode span:last-child").textContent = "Live workspace";
if (!currentSession.runs.length) showPlannerStatus("Ready for the first message pack.");

plannerInput.addEventListener("input", () => {
    uploadedMessageText = undefined;
    plannerFile.value = "";
});
plannerFile.addEventListener("change", async () => {
    const file = plannerFile.files[0];
    if (!file) return;
    uploadedMessageText = undefined;
    busy(true);
    showPlannerStatus("Reading " + file.name + "…");
    try {
        if (file.size > 8 * 1024 * 1024) throw new Error("Choose a file no larger than 8 MiB.");
        const bytes = new Uint8Array(await file.arrayBuffer());
        const chunks = [];
        for (let i = 0; i < bytes.length; i += 8192) {
            chunks.push(String.fromCharCode(...bytes.subarray(i, i + 8192)));
        }
        const data = await plannerRequest("/api/preview", {name: file.name, data: btoa(chunks.join(""))});
        uploadedMessageText = data.text;
        plannerInput.value = data.text;
        showPlannerStatus(file.name + " is ready. Review the text, then submit.");
    } catch (error) {
        plannerFile.value = "";
        showPlannerStatus(error.message, true);
    } finally {
        busy(false);
    }
});

plannerForm.addEventListener("submit", async event => {
    event.preventDefault();
    const text = uploadedMessageText ?? plannerInput.value;
    if (!text.trim()) {
        showPlannerStatus("Paste messages or choose a file.", true);
        return;
    }
    busy(true);
    showPlannerStatus("Running the planner…");
    try {
        const session = await plannerRequest("/api/run", {text});
        loadSession(session);
        currentSession = session;
        for (const {panel} of tabs.values()) panel.replaceChildren();
        activate("overview");
        updatePlannerControls(session);
        uploadStatus.textContent = "Live session";
        const latest = session.runs.at(-1);
        if (latest.status === "failed") {
            showPlannerStatus(latest.error || "Run failed. See AI Trace for details.", true);
        } else {
            showPlannerStatus("Run " + latest.number + " saved · " + (session.result?.status ?? "No plan yet"));
            plannerInput.value = "";
            plannerFile.value = "";
            uploadedMessageText = undefined;
        }
    } catch (error) {
        showPlannerStatus(error.message, true);
    } finally {
        busy(false);
    }
});
