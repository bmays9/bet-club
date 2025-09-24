console.log("Script loaded");

document.addEventListener("DOMContentLoaded", function () {
  // ===== Accordion score -> prediction color logic =====
  const accordionItems = document.querySelectorAll(".accordion-item");

  accordionItems.forEach(item => {
    const inputs = item.querySelectorAll(".score-input");
    inputs.forEach(input => {
      input.addEventListener("input", () => handlePredictionChange(item));
    });
  });

  function handlePredictionChange(leagueBlock) {
    const fixtureGroups = {};
    const inputs = leagueBlock.querySelectorAll(".score-input");

    // Gather scores per fixture
    inputs.forEach(input => {
      const fixtureId = input.dataset.fixtureId;
      const team = input.dataset.team;
      const value = input.value;

      if (!fixtureGroups[fixtureId]) fixtureGroups[fixtureId] = {};
      fixtureGroups[fixtureId][team] = value;
    });

    // Count predictions
    const predictionCount = { H: 0, D: 0, A: 0 };

    Object.values(fixtureGroups).forEach(({ home, away }) => {
      if (home !== undefined && away !== undefined && home !== '' && away !== '') {
        const h = parseInt(home);
        const a = parseInt(away);
        if (h > a) predictionCount.H++;
        else if (h < a) predictionCount.A++;
        else predictionCount.D++;
      }
    });

    // Reset all prediction cells in this league
    leagueBlock.querySelectorAll(".prediction-cell").forEach(cell => {
      cell.classList.remove("green", "red");
    });

    // Update colors based on counts
    ["H", "D", "A"].forEach(result => {
      const count = predictionCount[result];
      const cells = leagueBlock.querySelectorAll(`.prediction-cell[data-result="${result}"]`);
      if (count === 1) {
        cells.forEach(c => c.classList.add("green"));
      } else if (count > 1) {
        cells.forEach(c => c.classList.add("red"));
      }
    });
  }

  // ===== Submit button handler (only if it exists) =====
  const submitBtn = document.getElementById("submit-scores");
  if (submitBtn) {
    submitBtn.addEventListener("click", function () {
      if (!allLeaguesValid()) {
        alert("Each league must have exactly one prediction for H, D, and A.");
        return;
      }

     // Disable button to prevent duplicate clicks
     submitBtn.disabled = true;
     submitBtn.textContent = "Submitting...";

      const predictions = [];
      const scoreInputs = document.querySelectorAll(".score-input");
      const groupedByFixture = {};

      const groupSelect = document.getElementById("sp-group-select"); // select of groups
      const fixtureContainer = document.getElementById("fixture-container");

      if (!groupSelect || !fixtureContainer) {
        console.error("Required DOM elements not found");
        return;
      }

      const selectedGroupId = groupSelect.value;
      const gameTemplateId = fixtureContainer.dataset.templateId;

      // Build grouped scores
      scoreInputs.forEach(input => {
        const fixtureId = input.dataset.fixtureId;
        const team = input.dataset.team;
        const score = parseInt(input.value);

        if (!groupedByFixture[fixtureId]) {
          groupedByFixture[fixtureId] = {};
        }
        groupedByFixture[fixtureId][team] = score;
      });

      for (const [fixtureId, scores] of Object.entries(groupedByFixture)) {
        if (!isNaN(scores.home) && !isNaN(scores.away)) {
          predictions.push({
            fixture_id: fixtureId,
            home_score: scores.home,
            away_score: scores.away
          });
        }
      }

      const payload = {
        group_id: selectedGroupId,
        game_template_id: gameTemplateId,
        predictions: predictions
      };

      console.log("Submitting predictions JSON:", JSON.stringify(payload));
      const jsonCheck = isJsonString(JSON.stringify(payload));
      console.log("JSON Check:", jsonCheck);

      fetch("/scores/submit-predictions/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify(payload)
      })
        .then(response => response.json())
        .then(data => {
          if (data.status === "success") {
            alert("Predictions submitted!");
            window.location.reload();
          } else {
            alert("Failed to submit: " + (data.error || "Unknown error"));
          }
        });
    });
  } else {
    console.log("No submit button found — user may have already entered.");
  }

  // ===== Helpers (declared inside DOMContentLoaded for safety) =====
  function allLeaguesValid() {
    const leagueBlocks = document.querySelectorAll(".accordion-item");

    for (const leagueBlock of leagueBlocks) {
      const resultTypes = ["H", "D", "A"];
      for (const result of resultTypes) {
        const cells = leagueBlock.querySelectorAll(`.prediction-cell[data-result="${result}"]`);
        let greenCount = 0;

        cells.forEach(cell => {
          if (cell.classList.contains("green")) {
            greenCount++;
          }
        });

        // If not exactly one green cell per result in this league, fail validation
        if (greenCount !== 1) {
          return false;
        }
      }
    }

    return true;
  }

  function getCookie(name) {
    // Django requires CSRF tokens for POST requests made via JavaScript.
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

  function isJsonString(str) {
    try {
      JSON.parse(str);
    } catch (e) {
      return false;
    }
    return true;
  }

  // ===== Game summary loader (live card) =====
  const groupSelect = document.getElementById("sp-group-select");

  function loadGameSummary(groupId, templateSlug) {
  const summaryEl = document.getElementById("game-summary");
  const submitBtn = document.getElementById("submit-scores");
  if (!summaryEl || !submitBtn) return;

  fetch(`/scores/game-summary/${groupId}/${templateSlug}/`)
    .then(res => res.json())
    .then(data => {
      summaryEl.innerHTML = `
        <div class="card mb-3 text-white bg-info shadow-sm border rounded" style="max-width: 25rem;">
          <div class="card-header">${data.group_name}</div>
          <div class="card-body">
            <p class="card-text">Entries: ${data.player_count}</p>
            <p class="card-text">Prize Pot: £${data.pot}</p>
            <p class="card-text">Status: ${data.has_entered ? "Entered" : "Not yet entered"}</p>
            ${
              data.has_entered
                ? `<a href="/scores/game/${data.game_id}/" class="btn btn-primary">View Game</a>`
                : ""
            }
          </div>
        </div>
      `;

      // Show or hide submit button
      if (data.has_entered) {
        submitBtn.classList.add("d-none");
      } else {
        submitBtn.classList.remove("d-none");
      }
    })
    .catch(err => console.error("Error loading game summary:", err));
}


  if (groupSelect) {
    const slugEl = document.getElementById("game-template-slug");
    const templateSlug = slugEl ? slugEl.value : "";

    // Load for the initially selected group at page load
    loadGameSummary(groupSelect.value, templateSlug);

    // Load again when user changes dropdown
    groupSelect.addEventListener("change", function () {
      loadGameSummary(this.value, templateSlug);
    });
  }
}); // <-- closes DOMContentLoaded
