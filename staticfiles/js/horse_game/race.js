import { raceEntries, playerData, horseData, raceData, setRaceEntries, setHorseData, setPlayerData, setRaceData } from './gameState.js';
import { allEntries, canEnterRace, enterHorse, displayRaceEntries, allRacesHaveEntries } from './entry.js';
import { lineups , raceTime, meeting_number, going } from './horseracing.js';


let gameRaceNumber = -1

export function showRacecard (racenum) {

    gameRaceNumber ++
    const racecardBody = document.getElementById("racecard-body");
    console.log("Let's Race");
    racecardBody.innerHTML = ""; // clear previous
    let rDist = raceData.distances[gameRaceNumber];
    let rGoing = going[meeting_number];
    let rName = raceData.racenames[gameRaceNumber];
    let rTime = raceTime[racenum];
    let rPrize = raceData.prizemoney[gameRaceNumber];
    let entries = lineups[racenum];
    // Display Race Details
    const dTime = document.getElementById("r-time"); 
    dTime.innerHTML = rTime;
    const dName = document.getElementById("r-name");
    dName.innerHTML = rName;
    const dDist = document.getElementById("r-dist");
    dDist.innerHTML = rDist;
    const dPrize = document.getElementById("r-prize")
    dPrize.innerHTML = rPrize;
    const dRunners = document.getElementById("r-runners");
    dRunners.innerHTML = `${entries.length}`;

    let ratedHorses = getRatings(entries);
    ratedHorses = assignOdds(ratedHorses); // Adds odds based on ability
    
    console.log("This Lineup", lineups[racenum]);
    entries.forEach((entry, index) => {
        const horse = horseData.find(h => h.name === entry.horseName);
        const odds = `${ratedHorses[entry]}`;
        const row = `
            <tr>
                <td>${index + 1}</td>
                <td>${entry.horseName}</td>
                <td>${entry.trainer}</td>
                <td>${horse.form}</td>
                <td>${odds}</td>
            </tr>
        `;
        racecardBody.innerHTML += row;
    });

    // feed into the ratings system the horses, distance, going
    let racerRatings = getRatings(entries, rDist, rGoing )

    document.getElementById('start-race').addEventListener('click', function () {
        // Clear game state tables
        console.log("raceData in clear-game-state click:", raceData);
});
}

function getRatings(entries, distance, going) {
    return entries.map(entry => {
        const horse = horseData.find(h => h.name === entry.horseName);
        const ability = horse.rating + horse.form * 0.5 + horse.wins * 2 - horse.rest * 0.3;
        return { ...entry, ability, form: horse.form };
    });
}

function assignOdds(ratedHorses) {
    const maxAbility = Math.max(...ratedHorses.map(h => h.ability));
    return ratedHorses.map(horse => {
        const relativeChance = horse.ability / maxAbility;
        const impliedOdds = 1 / relativeChance;
        const formattedOdds = formatOdds(impliedOdds);
        return { ...horse, odds: formattedOdds };
    });
}

function formatOdds(decimal) {
    const numerator = Math.round((decimal - 1) * 2);
    return `${numerator}/2`;
}

function simulateRace(ratedHorses) {
    const raceResults = ratedHorses.map(horse => {
        const randomness = Math.random() * 0.2 + 0.9;
        const finalScore = horse.ability * randomness;
        return { ...horse, score: finalScore };
    });

    return raceResults.sort((a, b) => b.score - a.score);
}