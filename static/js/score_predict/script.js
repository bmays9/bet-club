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
