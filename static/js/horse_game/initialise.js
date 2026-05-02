// initialise.js
import { fetchTextFiles, players } from "./load_data.js";
import { allEntries, canEnterRace, enterHorse, displayRaceEntries } from './entry.js';
import { playerData, setPlayerData, horseData, setHorseData, raceData } from './gameState.js';

const STARTING_BALANCE = 50000;

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
        entries: 0,              // total entry fees paid (negative on total)
        prizeWinnings: 0,              // prize money from horse finishing places
        betStaked: 0,              // total staked on bets
        betReturned: 0,              // total returned from winning bets
        total: STARTING_BALANCE, // starting bankroll
        human: player.human,
        bettingProfile: null,          // set in runHorseRacing for AI players
        seasonHistory: []
    }));
}

export function buildHorseData(pool) {
    const horses = [];
    const adj = pool === true ? 144 : 0;

    for (let i = 0; i < 144; i++) {
        const baseRating = randomNormalRating();
        const bestDist = Math.floor(Math.random() * 28) + 5; // 5–32 furlongs

        let spread;
        if (bestDist <= 8) spread = parseFloat((1.0 + Math.random() * 1.5).toFixed(2));
        else if (bestDist <= 14) spread = parseFloat((2.0 + Math.random() * 2.0).toFixed(2));
        else spread = parseFloat((3.0 + Math.random() * 3.0).toFixed(2));

        const age = pool ? 4 : Math.floor(Math.random() * 7 + 4);
        const goingPref = getRandomGoingPreference();
        const nameRaw = raceData.horsenames[i + adj];
        const name = nameRaw || `Recruit ${i + 1}`;

        // Apply age modifier to initial rating
        const rating = adjustRatingByAge(baseRating, age);

        let owner;
        if (!pool) {
            const ownerIndex = Math.floor(i / 24);
            owner = playerData[ownerIndex]?.name || 'Unknown';
        }

        horses.push({
            number: i + 1 + adj,
            name,
            owner,
            baseRating,
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
    if (age <= 3) modifier = 0.82;
    else if (age === 4) modifier = 0.90;
    else if (age === 5) modifier = 0.95;
    else if (age >= 6 && age <= 8) modifier = 1.00; // peak
    else if (age === 9) modifier = 0.92;
    else if (age === 10) modifier = 0.83;
    return Math.round(baseRating * modifier);
}

export function endOfSeasonUpdate(horses) {
    for (const horse of horses) {
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
