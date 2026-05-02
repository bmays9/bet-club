// initialise.js
import { fetchTextFiles, players } from "./load_data.js";
import { allEntries, canEnterRace, enterHorse, displayRaceEntries } from './entry.js';
import { playerData, setPlayerData, horseData, setHorseData, raceData } from './gameState.js';

export function shuffleArray(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]];
    }
    return array;
}

export function getRandomGoingPreference() {
    const goings = ["Heavy", "Soft", "Good-Soft", "Good", "Good-Firm"];
    const weights = [5, 15, 40, 25, 15];
    const total = weights.reduce((s, w) => s + w, 0);
    let rand = Math.random() * total;
    for (let i = 0; i < goings.length; i++) {
        rand -= weights[i];
        if (rand < 0) return goings[i];
    }
    return goings[goings.length - 1];
}

export function resetPlayerData(playersList) {
    return playersList.map(player => ({
        name: player.name,
        wins: 0,
        betting: 0,
        entries: 0,
        winnings: 0,
        total: 0,
        human: player.human
    }));
}

export function buildHorseData(pool) {
    const horses = [];
    const adj = pool === true ? 144 : 0;

    for (let i = 0; i < 144; i++) {
        const rating = randomNormalRating();
        const bestDist = Math.floor(Math.random() * 28) + 5; // 5–32 furlongs

        // Spread = comfortable plateau either side of bestDist (furlongs).
        // Sprinters are tight specialists; stayers more versatile within staying trips.
        let spread;
        if (bestDist <= 8) {
            // Sprint (5–8f): plateau of 1.0–2.5f either side
            spread = parseFloat((1.0 + Math.random() * 1.5).toFixed(2));
        } else if (bestDist <= 14) {
            // Middle distance (9–14f): plateau of 2.0–4.0f either side
            spread = parseFloat((2.0 + Math.random() * 2.0).toFixed(2));
        } else {
            // Staying (15f+): plateau of 3.0–6.0f either side
            spread = parseFloat((3.0 + Math.random() * 3.0).toFixed(2));
        }

        const age = pool ? 4 : Math.floor(Math.random() * 7 + 4);
        const goingPref = getRandomGoingPreference();
        const name = raceData.horsenames[i + adj];

        let owner, ownerIndex;
        if (!pool) {
            ownerIndex = Math.floor(i / 24);
            owner = playerData[ownerIndex]?.name || 'Unknown';
        }

        horses.push({
            number: i + 1 + adj,
            name,
            owner,
            baseRating: rating,
            rating,
            bestDist,
            spread,
            goingPref,
            age,
            rest: 1,
            runs: 0,
            wins: 0,
            money: 0,
            form: "",
            history: [],
            grade1s: {}
        });
    }

    return horses;
}

export function adjustRatingByAge(baseRating, age) {
    let modifier = 1;
    if (age === 2) modifier = 0.70; // unraced youngsters
    else if (age === 3) modifier = 0.82;
    else if (age === 4) modifier = 0.90;
    else if (age === 5) modifier = 0.95;
    else if (age >= 6 && age <= 8) modifier = 1.00; // peak
    else if (age === 9) modifier = 0.90;
    else if (age === 10) modifier = 0.80;
    // 11+ retire at season start so no modifier needed
    return Math.round(baseRating * modifier);
}

export function endOfSeasonUpdate(horses) {
    for (let horse of horses) {
        horse.age++;
        horse.rating = adjustRatingByAge(horse.baseRating, horse.age);
    }
}

export function goingModifier(horseGoingPref, raceGoing) {
    const goings = ["Heavy", "Soft", "Good-Soft", "Good", "Good-Firm"];
    const distance = Math.abs(goings.indexOf(horseGoingPref) - goings.indexOf(raceGoing));
    if (distance === 0) return 1.00;
    if (distance === 1) return 0.95;
    if (distance === 2) return 0.85;
    return 0.75;
}

function randomNormalRating(mean = 110, stddev = 15, min = 70, max = 150) {
    let u = 0, v = 0;
    while (u === 0) u = Math.random();
    while (v === 0) v = Math.random();
    const raw = Math.round(mean + stddev * Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v));
    return Math.max(min, Math.min(max, raw));
}
