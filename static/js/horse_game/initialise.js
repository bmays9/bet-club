// load_data.js
import { fetchTextFiles } from "./load_data.js"; // Adjust the path if needed
import { allEntries, canEnterRace, enterHorse, displayRaceEntries } from './entry.js';
import { playerData, setPlayerData, horseData, setHorseData , raceData} from './gameState.js';

export function shuffleArray(array) {
    for (let i = array.length -1; i > 0 ; i--) {
        const j = Math.floor(Math.random() * (i + 1)); // Random index from 0 to i
        [array[i], array[j]] = [array[j], array[i]]; // Swap elements
    }
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
        total: 0
    }));
}
    
export function buildHorseData() {
    
    let horses = [];
    
    console.log("playerData:", playerData);

    for (let i = 0; i < 144; i++) {
        let rating = Math.floor(Math.random() * 101) + 10; // 10 to 110
        const bestDist = Math.floor(Math.random() * 28) + 5;  // 5 to 32
        const spread = parseFloat((Math.random() * 8 + 2).toFixed(2)); // 2.00 to 10.00
        let age = Math.floor(Math.random() * 7 + 4);
        let rest = 0;
        let form = "";
        const goingPref = getRandomGoingPreference();
        const name = raceData.horsenames[i];
        // Assign owner in chunks of 24
        const ownerIndex = Math.floor(i / 24);
        const owner = playerData[ownerIndex].name || `Unknown`;
        let number = i + 1
        let runs = 0, wins = 0, money = 0  
        
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
        });
    }

    return horses;
}

export function adjustRatingByAge(baseRating, age) {
    let modifier = 1;

    if (age === 4) modifier = 0.90;
    else if (age === 5) modifier = 0.95;
    else if (age >= 6 && age <= 8) modifier = 1.00;
    else if (age === 9) modifier = 0.95;
    else if (age === 10) modifier = 0.90;

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