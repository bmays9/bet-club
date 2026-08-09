console.log("Score Predict script loaded");

document.addEventListener("DOMContentLoaded", function () {
  const fixtureContainer = document.getElementById("fixture-container");
  if (!fixtureContainer) {
    console.log("No fixture container on this page — nothing to wire up.");
    return;
  }

  const leagueBlocks = fixtureContainer.querySelectorAll(".league-block");
  const submitButtons = document.querySelectorAll(".submit-scores-btn");

  // ===== Result helper =====
  function getFixtureResult(homeVal, awayVal) {
    if (homeVal === "" || awayVal === "" || homeVal === undefined || awayVal === undefined) {
      return null;
    }
    const h = parseInt(homeVal, 10);
    const a = parseInt(awayVal, 10);
    if (isNaN(h) || isNaN(a)) return null;
    if (h > a) return "H";
    if (h < a) return "A";
    return "D";
  }

  // ===== Per-league validation =====
  // Rule:
  //  - League has >= 3 fixtures listed -> exactly 1 Home win, 1 Away win, 1 Draw. No more, no fewer.
  //  - League has < 3 fixtures listed  -> no predictions allowed at all.
  function validateLeague(block) {
    const fixtureCount = parseInt(block.dataset.fixtureCount, 10) || 0;
    const fixtureItems = block.querySelectorAll(".fixture-item");

    const results = [];
    fixtureItems.forEach(item => {
      const homeInput = item.querySelector('.score-input[data-team="home"]');
      const awayInput = item.querySelector('.score-input[data-team="away"]');
      if (!homeInput || !awayInput) return;
      const result = getFixtureResult(homeInput.value, awayInput.value);
      if (result) results.push(result);
    });

    let valid = true;
    let message = "";

    if (fixtureCount < 3) {
      if (results.length > 0) {
        valid = false;
        message = "No predictions allowed (fewer than 3 fixtures)";
      }
    } else {
      const counts = { H: 0, D: 0, A: 0 };
      results.forEach(r => counts[r]++);
      const total = results.length;

      if (total < 3) {
        const remaining = 3 - total;
        valid = false;
        message = `Need ${remaining} more pick${remaining === 1 ? "" : "s"} (1 Home, 1 Away, 1 Draw)`;
      } else if (total > 3 || counts.H !== 1 || counts.D !== 1 || counts.A !== 1) {
        valid = false;
        message = "Must be exactly 1 Home win, 1 Away win, 1 Draw";
      } else {
        message = "\u2713 Complete";
      }
    }

    block.dataset.valid = valid ? "true" : "false";

    const statusEl = block.querySelector(".league-status");
    if (statusEl) {
      statusEl.textContent = message;
      statusEl.classList.toggle("text-danger", !valid);
      statusEl.classList.toggle("text-success", valid && message !== "");
    }

    return valid;
  }

  function validateAll() {
    let allValid = true;
    leagueBlocks.forEach(block => {
      if (!validateLeague(block)) allValid = false;
    });

    submitButtons.forEach(btn => {
      btn.disabled = !allValid;
      btn.classList.toggle("disabled", !allValid);
    });

    return allValid;
  }

  // Re-validate on every score change
  fixtureContainer.querySelectorAll(".score-input").forEach(input => {
    input.addEventListener("input", validateAll);
  });

  // Run once on load so buttons start in the correct (disabled) state
  validateAll();

  // ===== Submit handling (one button per group, sharing the same predictions) =====
  submitButtons.forEach(btn => {
    btn.addEventListener("click", function () {
      if (!validateAll()) {
        alert("Each league needs exactly one Home win, one Away win, and one Draw prediction. Leagues with fewer than 3 fixtures can't have any predictions.");
        return;
      }

      const groupId = btn.dataset.groupId;
      const templateId = btn.dataset.templateId;
      const originalText = btn.textContent;

      btn.disabled = true;
      btn.textContent = "Submitting...";

      const predictions = [];
      fixtureContainer.querySelectorAll(".fixture-item").forEach(item => {
        const fixtureId = item.dataset.fixtureId;
        const homeInput = item.querySelector('.score-input[data-team="home"]');
        const awayInput = item.querySelector('.score-input[data-team="away"]');
        if (!homeInput || !awayInput) return;

        const h = parseInt(homeInput.value, 10);
        const a = parseInt(awayInput.value, 10);
        if (!isNaN(h) && !isNaN(a)) {
          predictions.push({
            fixture_id: fixtureId,
            home_score: h,
            away_score: a,
          });
        }
      });

      const payload = {
        group_id: groupId,
        game_template_id: templateId,
        predictions: predictions,
      };

      fetch("/scores/submit-predictions/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify(payload),
      })
        .then(response => response.json())
        .then(data => {
          if (data.status === "success") {
            alert("Predictions submitted!");
            window.location.reload();
          } else {
            alert("Failed to submit: " + (data.error || "Unknown error"));
            btn.disabled = false;
            btn.textContent = originalText;
          }
        })
        .catch(err => {
          console.error("Error submitting predictions:", err);
          alert("Something went wrong submitting your predictions.");
          btn.disabled = false;
          btn.textContent = originalText;
        });
    });
  });

  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + "=")) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }
});