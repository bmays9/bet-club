document.addEventListener("DOMContentLoaded", function () {
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
        const h = parseInt(home), a = parseInt(away);
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
});


document.getElementById("submit-scores").addEventListener("click", function () {
    const predictions = [];

    const scoreInputs = document.querySelectorAll(".score-input");
    const groupedByFixture = {};

    // Optional: Replace with how you store these in JS (e.g. via data attributes)
    const groupId = document.getElementById("group-id").value;  // or data-group-id attribute
    const gameTemplateId = document.getElementById("game-template-id").value;  // or data-template-id

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
        if (scores.home != null && scores.away != null) {
            predictions.push({
                fixture_id: fixtureId,
                home_score: scores.home,
                away_score: scores.away
            });
        }
    }

    fetch("/submit-predictions/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify({
            group_id: groupId,
            game_template_id: gameTemplateId,
            predictions: predictions
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert("Predictions submitted!");
            window.location.reload();
        } else {
            alert("Failed to submit: " + (data.error || "Unknown error"));
        }
    });
});
