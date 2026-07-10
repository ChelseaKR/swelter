(() => {
  "use strict";

  const form = document.querySelector("#decision-form");
  const modelNode = document.querySelector("#decision-model");
  const progress = document.querySelector("#progress");
  const error = document.querySelector("#form-error");
  const empty = document.querySelector("#result-empty");
  const result = document.querySelector("#result");
  const copyButton = document.querySelector("#copy-plan");
  const printButton = document.querySelector("#print-plan");
  const copyStatus = document.querySelector("#copy-status");

  if (!form || !modelNode || !progress || !error || !empty || !result) return;

  const fieldLabels = {
    goal: "Decision",
    evidence: "Evidence today",
    timeline: "Decision window",
    stewardship: "Stewardship",
    governance: "Community mandate",
    calibration: "Calibration path",
  };

  let model;
  let currentPlan = "";

  try {
    model = JSON.parse(modelNode.textContent);
    const invalidRule = model.rules.find((rule) => !model.outcomes[rule.outcome]);
    if (!Array.isArray(model.required) || invalidRule) throw new Error("Invalid decision model");
  } catch (_modelError) {
    error.textContent = "The decision guide could not load. The stop/go gates below still apply.";
    error.hidden = false;
    form.querySelector("button[type='submit']").disabled = true;
    return;
  }

  function answersFromForm() {
    const values = new FormData(form);
    return Object.fromEntries(model.required.map((field) => [field, values.get(field)]));
  }

  function termMatches(term, answers) {
    return Array.isArray(term.in) && term.in.includes(answers[term.field]);
  }

  function conditionMatches(condition, answers) {
    if (condition.all) return condition.all.every((term) => termMatches(term, answers));
    if (condition.any) return condition.any.some((term) => termMatches(term, answers));
    return false;
  }

  function recommendationFor(answers) {
    const rule = model.rules.find(
      (candidate) => !candidate.when || conditionMatches(candidate.when, answers),
    );
    if (!rule) throw new Error("No recommendation matched");
    return { ...model.outcomes[rule.outcome], ruleId: rule.id };
  }

  function selectedLabel(field) {
    const selected = form.querySelector(`input[name="${field}"]:checked`);
    return selected?.closest("label")?.querySelector("strong")?.textContent?.trim() || "—";
  }

  function replaceList(selector, values) {
    const list = result.querySelector(selector);
    list.replaceChildren();
    for (const value of values) {
      const item = document.createElement("li");
      item.textContent = value;
      list.append(item);
    }
  }

  function buildAnswerRecord() {
    const record = result.querySelector("#answer-record");
    record.replaceChildren();
    for (const field of model.required) {
      const term = document.createElement("dt");
      const description = document.createElement("dd");
      term.textContent = fieldLabels[field];
      description.textContent = selectedLabel(field);
      record.append(term, description);
    }
  }

  function planAsText(recommendation) {
    const lines = [
      "SWELTER PROJECT DECISION",
      recommendation.decision,
      recommendation.title,
      "",
      recommendation.why,
      "",
      "INPUTS",
      ...model.required.map((field) => `${fieldLabels[field]}: ${selectedLabel(field)}`),
      "",
      "NEXT MOVES",
      ...recommendation.next_steps.map((step, index) => `${index + 1}. ${step}`),
      "",
      "PROOF BEFORE THE NEXT GATE",
      ...recommendation.proof.map((item) => `- [ ] ${item}`),
      "",
      "RED LINES",
      ...recommendation.red_lines.map((item) => `- ${item}`),
      "",
      "Generated locally by the swelter project planner. No answers were stored or transmitted.",
    ];
    return lines.join("\n");
  }

  function renderRecommendation(recommendation) {
    result.querySelector("#result-decision").textContent = recommendation.decision;
    result.querySelector("#result-title").textContent = recommendation.title;
    result.querySelector("#result-why").textContent = recommendation.why;
    replaceList("#result-steps", recommendation.next_steps);
    replaceList("#result-proof", recommendation.proof);
    replaceList("#result-red-lines", recommendation.red_lines);
    buildAnswerRecord();
    currentPlan = planAsText(recommendation);
    copyStatus.textContent = "";
    empty.hidden = true;
    result.hidden = false;
    result.focus({ preventScroll: true });
    result.scrollIntoView({ block: "start" });
  }

  function updateProgress() {
    const answered = model.required.filter(
      (field) => form.querySelector(`input[name="${field}"]:checked`) !== null,
    ).length;
    progress.textContent = `${answered} of ${model.required.length} answered`;
  }

  form.addEventListener("input", () => {
    error.hidden = true;
    updateProgress();
  });

  form.addEventListener("reset", () => {
    window.setTimeout(() => {
      updateProgress();
      error.hidden = true;
      result.hidden = true;
      empty.hidden = false;
      currentPlan = "";
      copyStatus.textContent = "";
    }, 0);
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const answers = answersFromForm();
    const missing = model.required.filter((field) => !answers[field]);
    if (missing.length) {
      error.textContent = `Answer all six questions. ${missing.length} ${missing.length === 1 ? "answer is" : "answers are"} still missing.`;
      error.hidden = false;
      error.focus();
      form.querySelector(`input[name="${missing[0]}"]`)?.focus();
      return;
    }
    renderRecommendation(recommendationFor(answers));
  });

  async function copyPlan() {
    if (!currentPlan) return;
    try {
      await navigator.clipboard.writeText(currentPlan);
    } catch (_clipboardError) {
      const transfer = document.createElement("textarea");
      transfer.value = currentPlan;
      transfer.setAttribute("aria-hidden", "true");
      transfer.style.position = "fixed";
      transfer.style.opacity = "0";
      document.body.append(transfer);
      transfer.select();
      document.execCommand("copy");
      transfer.remove();
    }
    copyStatus.textContent = "Plan copied. Nothing was sent or saved.";
  }

  copyButton?.addEventListener("click", copyPlan);
  printButton?.addEventListener("click", () => window.print());
  updateProgress();
})();
