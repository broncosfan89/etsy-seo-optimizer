const extractForm = document.getElementById("extract-form");
const analysisForm = document.getElementById("analysis-form");
const listingUrlInput = document.getElementById("listing-url");
const extractButton = document.getElementById("extract-button");
const analyzeButton = document.getElementById("analyze-button");
const statusPanel = document.getElementById("status-panel");
const editorCard = document.getElementById("editor-card");
const resultsCard = document.getElementById("results-card");
const notesList = document.getElementById("notes-list");
const confidencePill = document.getElementById("confidence-pill");
const currentTitle = document.getElementById("current-title");
const currentDescription = document.getElementById("current-description");
const categoryInput = document.getElementById("category");
const keywordInput = document.getElementById("target-keyword");
const scoreValue = document.getElementById("score-value");
const scoreLabel = document.getElementById("score-label");
const scoreMeta = document.getElementById("score-meta");
const issuesList = document.getElementById("issues-list");
const keywordFocus = document.getElementById("keyword-focus");
const optimizedTitle = document.getElementById("optimized-title");
const optimizedDescription = document.getElementById("optimized-description");
const suggestedTags = document.getElementById("suggested-tags");
const explanation = document.getElementById("explanation");

const originalButtons = new Map();
document.querySelectorAll("button").forEach((button) => {
    originalButtons.set(button, button.textContent);
});

extractForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    resultsCard.classList.add("hidden");
    setStatus("Extracting title and description from the public listing page...", "warn");
    setButtonLoading(extractButton, true, "Extracting...");

    try {
        const response = await postJson("/extract", { url: listingUrlInput.value.trim() });
        populateEditor(response);

        const message = !response.success
            ? "Public extraction failed. Enter the listing details manually below and continue with analysis."
            : response.fallback_required
                ? "Extraction was partial. Review the fields below and fill in anything missing before analysis."
                : "Extraction looks usable. Review the fields below, make edits if needed, then generate SEO recommendations.";

        setStatus(message, response.success && !response.fallback_required ? "success" : "warn");
    } catch (error) {
        populateEditor({
            confidence: 0,
            extracted_title: "",
            extracted_description: "",
            extraction_notes: ["Public extraction failed. Enter the listing details manually to continue."],
            fallback_required: true,
        });
        setStatus(error.message || "Extraction failed. Manual entry is available below.", "warn");
    } finally {
        setButtonLoading(extractButton, false);
    }
});

analysisForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setStatus("Running SEO analysis and generating improved copy...", "warn");
    setButtonLoading(analyzeButton, true, "Analyzing...");

    try {
        const payload = {
            title: currentTitle.value.trim(),
            description: currentDescription.value.trim(),
            category: categoryInput.value.trim(),
            target_keyword: keywordInput.value.trim(),
        };

        const response = await postJson("/analyze", payload);
        renderResults(response);
        setStatus("Analysis complete. Copy the updated title, description, or tags directly from the results.", "success");
    } catch (error) {
        setStatus(error.message || "Analysis failed. Check your LLM settings or try again.", "warn");
    } finally {
        setButtonLoading(analyzeButton, false);
    }
});

document.addEventListener("click", async (event) => {
    const button = event.target.closest(".copy-button");
    if (!button) {
        return;
    }

    const targetId = button.dataset.copyTarget;
    let text = "";

    if (targetId === "suggested-tags") {
        text = Array.from(suggestedTags.querySelectorAll(".tag"))
            .map((tag) => tag.textContent.trim())
            .join(", ");
    } else {
        const target = document.getElementById(targetId);
        text = target ? target.value : "";
    }

    if (!text) {
        return;
    }

    try {
        await navigator.clipboard.writeText(text);
        const original = button.textContent;
        button.textContent = "Copied";
        window.setTimeout(() => {
            button.textContent = original;
        }, 1200);
    } catch (error) {
        setStatus("Clipboard access failed. You can still select and copy the text manually.", "warn");
    }
});

async function postJson(url, payload) {
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        const message = data?.detail?.message || data?.message || "Request failed.";
        throw new Error(message);
    }
    return data;
}

function populateEditor(response) {
    editorCard.classList.remove("hidden");
    confidencePill.textContent = `Confidence ${((response.confidence || 0) * 100).toFixed(0)}%`;
    currentTitle.value = response.extracted_title || "";
    currentDescription.value = response.extracted_description || "";
    renderNotes(response.extraction_notes || []);
    editorCard.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderNotes(notes) {
    notesList.innerHTML = "";
    notes.forEach((note) => {
        const item = document.createElement("div");
        item.className = `note ${noteToneClass(note)}`.trim();
        item.textContent = note;
        notesList.appendChild(item);
    });
}

function renderResults(response) {
    resultsCard.dataset.scoreBand = scoreBand(response.seo_score);
    scoreValue.textContent = response.seo_score;
    scoreLabel.textContent = response.score_label;
    scoreMeta.textContent = response.used_mock ? "Mock output" : "LLM output";
    keywordFocus.textContent = response.keyword_focus || "No keyword focus returned";
    optimizedTitle.value = response.optimized_title || "";
    optimizedDescription.value = response.optimized_description || "";
    explanation.textContent = response.explanation || "";

    issuesList.innerHTML = "";
    (response.issues_found || []).forEach((issue) => {
        const item = document.createElement("li");
        item.textContent = issue;
        issuesList.appendChild(item);
    });

    suggestedTags.innerHTML = "";
    (response.suggested_tags || []).forEach((tag) => {
        const pill = document.createElement("span");
        pill.className = "tag";
        pill.textContent = tag;
        suggestedTags.appendChild(pill);
    });

    resultsCard.classList.remove("hidden");
    resultsCard.scrollIntoView({ behavior: "smooth", block: "start" });
}

function setStatus(message, tone) {
    if (!message) {
        statusPanel.innerHTML = "";
        return;
    }

    statusPanel.innerHTML = `<div class="status-message ${tone || ""}">${escapeHtml(message)}</div>`;
}

function setButtonLoading(button, loading, label) {
    button.disabled = loading;
    button.textContent = loading ? label : originalButtons.get(button);
}

function scoreBand(score) {
    if (score >= 85) {
        return "strong";
    }
    if (score >= 70) {
        return "good";
    }
    if (score >= 40) {
        return "needs-work";
    }
    return "poor";
}

function noteToneClass(note) {
    const value = (note || "").toLowerCase();
    if (value.includes("blocked") || value.includes("captcha")) {
        return "note-danger";
    }
    if (value.includes("manual") || value.includes("confidence") || value.includes("short")) {
        return "note-warn";
    }
    return "";
}

function escapeHtml(value) {
    return value
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
}
