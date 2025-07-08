// load_data.js
import { fetchTextFiles, players } from "./load_data.js"; // Adjust the path if needed
import { allEntries, canEnterRace, enterHorse, displayRaceEntries } from './entry.js';
import { playerData, setPlayerData, horseData, setHorseData , raceData} from './gameState.js';

export function shuffleArray(array) {
    for (let i = array.length -1; i > 0 ; i--) {
        const j = Math.floor(Math.random() * (i + 1)); // Random index from 0 to i
        [array[i], array[j]] = [array[j], array[i]]; // Swap elements
    }
    return array;
}


export function getRandomGoingPreference() {
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

export function horseRating(distance, peakDistance, maxRating, spread) {
    const exponent = -Math.pow(distance - peakDistance, 2) / (2 * Math.pow(spread, 2));
    return maxRating * Math.exp(exponent);
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
    
export function buildHorseData() {
    
    let horses = [];
    
    console.log("playerData:", playerData);

    for (let i = 0; i < 144; i++) {
        // let rating = Math.floor(Math.random() * 81) + 70; // 70 to 150 - uses even distribution.
        let rating = randomNormalRating();
        const bestDist = Math.floor(Math.random() * 28) + 5;  // 5 to 32
        let spread;
        if (bestDist < 13) {
            spread = parseFloat((Math.random() * 2 + 1).toFixed(2)); // 1.00 to 3.00
        } else {
            spread = parseFloat((Math.random() * 4 + 2).toFixed(2)); // 2.00 to 6.00
        }
        
        let age = Math.floor(Math.random() * 7 + 3);
        let rest = 1;
        let form = "";
        const goingPref = getRandomGoingPreference();
        const name = raceData.horsenames[i];
        // Assign owner in chunks of 24
        const ownerIndex = Math.floor(i / 24);
        const owner = playerData[ownerIndex].name || `Unknown`;
        let number = i + 1
        let runs = 0, wins = 0, money = 0  
        let history = [];
        
        horses.push({
            number,
            name,
            owner,
            baseRating: rating,
            rating,
            bestDist,
            spread,
            goingPref,
            age,
            rest,
            runs,
            form,
            wins,
            money,
            history,
        });
    }

    return horses;
}

export function adjustRatingByAge(baseRating, age) {
    let modifier = 1;

    if (age === 4) modifier = 0.90;
    else if (age === 5) modifier = 0.95;
    else if (age >= 6 && age <= 8) modifier = 1.00;
    else if (age === 9) modifier = 0.90;
    else if (age === 10) modifier = 0.80;

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

    const prefIndex = goings.indexOf(horseGoingPref);
    const raceIndex = goings.indexOf(raceGoing);

    const distance = Math.abs(prefIndex - raceIndex);

    if (distance === 0) return 1.0;
    if (distance === 1) return 0.95;
    if (distance === 2) return 0.85;
    return 0.75;
}

function randomNormalRating(mean = 110, stddev = 15, min = 70, max = 150) {
    let u = 0, v = 0;
    while (u === 0) u = Math.random(); // avoid 0
    while (v === 0) v = Math.random();
    let standardNormal = Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
    let rating = Math.round(mean + stddev * standardNormal);

    // Clamp to valid range
    return Math.max(min, Math.min(max, rating));
}