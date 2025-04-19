import { raceEntries } from './gameState.js';

export let allEntries = {
    "Player 1": { 0: [], 1: [], 2: [], 3: [], 4: [], 5: [] },
    "Player 2": { 0: [], 1: [], 2: [], 3: [], 4: [], 5: [] },
    "Player 3": { 0: [], 1: [], 2: [], 3: [], 4: [], 5: [] },
    "Player 4": { 0: [], 1: [], 2: [], 3: [], 4: [], 5: [] },
    "Player 5": { 0: [], 1: [], 2: [], 3: [], 4: [], 5: [] },
    "Player 6": { 0: [], 1: [], 2: [], 3: [], 4: [], 5: [] },
  };

export function canEnterRace(playerName, horseName, raceIndex) {
    // Check if horse is already entered
    console.log("Can it Enter?")
    for (let entries of Object.values(raceEntries)) {
        if (entries.some(e => e.horseName === horseName)) return false;
    }

    // Check player hasn't used 3 entries in this race
    console.log("RaceEntries in canEnterRace", raceEntries)
    console.log("raceEntries:", raceEntries);
    console.log("raceIndex:", raceIndex);
    const entriesInRace = raceEntries[raceIndex].length
    return entriesInRace < 3;
}

export function enterHorse(playerName, horseName, raceIndex) {
    if (canEnterRace(playerName, horseName, raceIndex)) {
        raceEntries[raceIndex].push({ playerName, horseName });
        console.log("Horse Is Entered")
        return true;
    }
    return false;
}

export function displayRaceEntries(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    let html = "";
    for (let i = 0; i < 6; i++) {
        html += `<h4>Race ${i + 1}</h4><ul>`;
        for (let entry of raceEntries[i]) {
            html += `<li>${entry.horseName} (${entry.playerName})</li>`;
        }
        html += `</ul>`;
    }
    container.innerHTML = html;
}

export function allRacesHaveEntries() {
    console.log("All Races have entries")
    for (let i = 0; i < 6; i++) {
        if (!raceEntries[i] || raceEntries[i].length === 0) {
            console.log("Nope")
            return false; // At least one race is empty
        }
    }
    console.log("Yes")
    return true; // Every race has at least one entry
}

