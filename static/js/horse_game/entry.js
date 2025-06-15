import {
    raceEntries,
    playerData,
    horseData,
    raceData,
    setRaceEntries,
    setHorseData,
    setPlayerData,
    setRaceData,
    sortPlayerData
} from './gameState.js';

import {
    shuffleArray
} from './initialise.js';

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

export function computerAutoSelect(playerName, meeting) {
    let selectedHorses = [];
        
    let playerHorses = horseData.filter(horse => horse.owner === playerName);
    console.log("playerHorses: comp select", playerHorses)
    console.log("meeting: comp select", meeting)

    if (meeting === 0) {
        selectedHorses = playerHorses.slice(0, 8);
    } else if (meeting === 1) {
        selectedHorses = playerHorses.slice(8, 16);
    } else if (meeting === 2) {
        selectedHorses = playerHorses.slice(16, 24);
    }

    console.log("selectedHorses: comp select", selectedHorses)

    // Initialize race entries
    for (let i = 0; i < 6; i++) {
        raceEntries[i] = raceEntries[i] || [];
    }

    // Assign 1 horse to each of the 6 races
    for (let i = 0; i < 6; i++) {
        raceEntries[i].push({
            playerName,
            horseName: selectedHorses[i].name
        });
    }

    // Randomly assign 2 extra horses to different races
    const extraRaces = shuffleArray([0, 1, 2, 3, 4, 5]).slice(0, 2);
    raceEntries[extraRaces[0]].push({
        playerName,
        horseName: selectedHorses[6].name
    });
    raceEntries[extraRaces[1]].push({
        playerName,
        horseName: selectedHorses[7].name
    });
}


export function computerSelect(playerName, meetingNumber) {
    const playerHorses = horseData.filter(h => h.owner === playerName);
    const startIndex = (meetingNumber) * 6;
    const endIndex = startIndex + 6;

    const availableRaces = [];
    for (let i = startIndex; i < endIndex; i++) {
        availableRaces.push({
            distance: raceData.distances[i],
            raceClass: raceData.raceclass[i],
            index: i - startIndex
        });
    }
    console.log("TIme to pick Horses!")
    console.log("Races Available", availableRaces)

    // Initialize race entries
    for (let i = 0; i < 6; i++) {
        raceEntries[i] = raceEntries[i] || [];
    }

    console.log("raceEntries", raceEntries)

    const entriesPerRace = Array.from({ length: 6 }, (_, i) => (raceEntries[i] || []).length); // ✅ safe
    const selectedHorses = new Set();
    const restPriority = [2, 3, 4, 5, 6]; // preferred order of rest values

    const prioritizedHorses = [];
    for (let restValue of restPriority) {
        const filtered = playerHorses.filter(h => h.rest === restValue && !selectedHorses.has(h.name));
        prioritizedHorses.push(...filtered);
    }

    console.log("Prioritised Horses", prioritizedHorses)

    for (let horse of prioritizedHorses) {
        if (horse.rest <= 1) continue;

        const runDistances = (horse.history || []).map(h => h.distance);
        const winDistances = (horse.history || [])
            .filter(h => h.position === 1)
            .map(h => h.distance);

        let entered = false;

        console.log("Run / Win DIstances for", horse.name, runDistances, winDistances)

        // 1. Prioritize winning distances
        for (let race of availableRaces) {
            if (winDistances.includes(race.distance) && entriesPerRace[race.index] < 3) {
                console.log("THERE WAS A WINNING MATCH! For" , horse.name)
                raceEntries[race.index].push({
                    playerName,
                    horseName: horse.name
                });
                entriesPerRace[race.index]++;
                selectedHorses.add(horse.name);
                entered = true;
                break;
            }
        }
        console.log("Entered Winning Match?", entered)
        if (entered) continue;

        // 2. Otherwise, use suitability and prefer empty races
        const sortedRaces = availableRaces
            .map(race => ({
                ...race,
                hasRunDistance: runDistances.includes(race.distance)
            }))
            .sort((a, b) => {
                if (entriesPerRace[a.index] === 0 && entriesPerRace[b.index] > 0) return -1;
                if (entriesPerRace[a.index] > 0 && entriesPerRace[b.index] === 0) return 1;
                return a.raceClass - b.raceClass;
            });

        for (let race of sortedRaces) {
            if (entriesPerRace[race.index] >= 3) continue;
            if (race.raceClass === 1 && !race.hasRunDistance) continue;
            if (race.raceClass === 2 && horse.rest < 3 && !race.hasRunDistance) continue;
            if (race.raceClass === 4 && race.hasRunDistance) continue;

            raceEntries[race.index].push({
                playerName,
                horseName: horse.name
            });
            entriesPerRace[race.index]++;
            selectedHorses.add(horse.name);
            break;
        }
    }
}

export function getRestIndicator(rest) {

    let color;
    let displayRest = rest;

    switch (rest) {
        case 0: color = "red"; break;
        case 1: color = "orange"; break;
        case 2: color = "forestgreen"; break;
        case 3: color = "lightgreen"; break;
        case 4: color = "turquoise"; break;
        default: color = "tan"; displayRest = "="; break;
    }

    return `<span style="
        display: inline-block;
        width: 20px;
        height: 20px;
        line-height: 20px;
        border-radius: 50%;
        background-color: ${color};
        color: white;
        text-align: center;
        font-weight: bold;
        font-size: 12px;
    ">${displayRest}</span>`;
}