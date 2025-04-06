import { fetchTextFiles } from "./load_data.js"; // Adjust the path if needed

let meeting_number = 0;
let players = []
const TOTALHORSES = 144
let raceData = {}; // Declare raceData globally
let playerData = {};
let horseData = {};


async function getRaceData() {
    raceData = await fetchTextFiles();
    console.log("Race data in another file:", raceData);
    
    // Example usage
    console.log("Horsenames:", raceData.horsenames);
    shuffleArray(raceData.horsenames); // Shuffle the array
    raceData.horsenames = raceData.horsenames.slice(0, TOTALHORSES) // only need 6 * 24
    console.log("Horsenames:", raceData.horsenames);

}

function shuffleArray(array) {
    for (let i = 0; i < TOTALHORSES; i++) {
        const j = Math.floor(Math.random() * (i + 1)); // Random index from 0 to i
        [array[i], array[j]] = [array[j], array[i]]; // Swap elements
    }
}


function getRandomGoingPreference() {
    const goings = ["Heavy", "Soft", "Good-Soft", "Good", "Good-Firm"];
    const weights = [5, 15, 40, 25, 15]; // Must match order of goings

    const totalWeight = weights.reduce((sum, w) => sum + w, 0);
    const rand = Math.random() * totalWeight;

    let cumulative = 0;
    for (let i = 0; i < goings.length; i++) {
        cumulative += weights[i];
        if (rand < cumulative) return goings[i];
    }

    return goings[goings.length - 1]; // Fallback
}

function horseRating(distance, peakDistance, maxRating, spread) {
    const exponent = -Math.pow(distance - peakDistance, 2) / (2 * Math.pow(spread, 2));
    return maxRating * Math.exp(exponent);
}

function setPlayerData() {
    
    let plyr = [];
    let wins = 0;
    let betting = 0;
    let entries = 0;
    let winnings = 0;
    let total = 0;

    for (let i = 0; i < 6; i++){
        name = players[i];
        
        plyr.push({
            name,
            wins,
            betting,
            entries,
            winnings,
            total
        })
    }
    
    return plyr
}

function buildHorseData() {
    
    let horses = [];

    for (let i = 0; i < TOTALHORSES; i++) {
        let rating = Math.floor(Math.random() * 101) + 10; // 10 to 110
        const bestDist = Math.floor(Math.random() * 28) + 5;  // 5 to 32
        const spread = parseFloat((Math.random() * 8 + 2).toFixed(2)); // 2.00 to 10.00
        let age = Math.floor(Math.random() * 7 + 4);
        let rest = 0
        const goingPref = getRandomGoingPreference();
        const name = raceData.horsenames[i];

        horses.push({
            name,
            baseRating: rating,
            rating,
            bestDist,
            spread,
            goingPref,
            age,
            rest
        });
    }

    return horses;
}

function adjustRatingByAge(baseRating, age) {
    let modifier = 1;

    if (age === 4) modifier = 0.90;
    else if (age === 5) modifier = 0.95;
    else if (age >= 6 && age <= 8) modifier = 1.00;
    else if (age === 9) modifier = 0.95;
    else if (age === 10) modifier = 0.90;

    return Math.round(baseRating * modifier);
}

function endOfSeasonUpdate(horses) {
    for (let horse of horses) {
        horse.age++;
        horse.rating = adjustRatingByAge(horse.baseRating, horse.age);
    }
}

function goingModifier(horseGoingPref, raceGoing) {
    const goings = ["Heavy", "Soft", "Good-Soft", "Good", "Good-Firm"];

    const prefIndex = goings.indexOf(horseGoingPref);
    const raceIndex = goings.indexOf(raceGoing);

    const distance = Math.abs(prefIndex - raceIndex);

    if (distance === 0) return 1.0;
    if (distance === 1) return 0.95;
    if (distance === 2) return 0.85;
    return 0.75;
}
function displayGameState(array) {

    console.log("Checking raceData:", raceData);

    if (!raceData || !raceData.distances) {
        console.error("Race data is not loaded yet.");
        return;
    }
    let tableHtml = "";
    tableHtml = `<tr>
                <th>Time</th>
                <th>Distance</th>
                <th>Name</th>
                <th>Prize Money</th>
                </tr>`;
    
    for (let i = 0; i < 6; i++) {
        tableHtml += 
            `<tr>
            <td>1.15</td>
            <td>${raceData.distances[meeting_number * 6 + i]}</td>
            <td>${raceData.racenames[meeting_number * 6 + i]}</td>
            <td>${raceData.prizemoney[meeting_number * 6 + i]}</td>
            </tr>`;
                }
    
    document.getElementById('gs-meeting-races').innerHTML = tableHtml;

    // Player data
}


async function runHorseRacing() {

    await getRaceData();
    horseData = buildHorseData();
    playerData = setPlayerData();
    displayGameState(meeting_number);


    // End of season:
    endOfSeasonUpdate(horseData);

}



document.addEventListener("DOMContentLoaded", () => {
    runHorseRacing();
});

